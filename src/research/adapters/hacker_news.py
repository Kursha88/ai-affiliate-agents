"""Hacker News source adapter for Researcher 2.0.

Responsibility boundary (Stage 3.2):

    HN Firebase API -> source-level parsing/filtering -> RawDiscovery[]

This adapter does NOT classify clusters, verify claims or provenance,
compute ``CandidateScore`` components, rank candidates or decide what
gets published. The only filtering applied is source-level hygiene —
supported item type, valid title, freshness window, dead/deleted/
malformed items. There is deliberately NO AI-keyword prefiltering and
NO composite scoring here (legacy NewsHunter's ``ai_score`` /
``final_score`` are strategic-ranking logic and were not transplanted);
classification belongs to the later pipeline stage. All valid fresh
stories are returned in HN's own topstories order (source-native
ordering, not our ranking).

Source URL rule:
- Story WITH an outbound URL -> ``url`` is the OUTBOUND article/project
  URL; the HN discussion URL is kept in ``metadata["hn_item_url"]``
  only. HN must not pretend to be the primary source of an external
  claim.
- Text-only / Ask HN / Show HN item WITHOUT an outbound URL -> no
  external primary source is fabricated. The HN discussion URL is used
  as the discovery's own source URL and the record is explicitly marked
  ``metadata["hn_native"] = True``.

Network design:
- All HTTP flows through an injected ``fetch_json`` callable
  (URL -> parsed JSON or ``None``). The module performs no I/O at import
  time; ``HackerNewsAdapter()`` wires a requests-based default for
  production, while tests inject fakes and need zero live internet.
- A ``None``/invalid topstories response raises ``HackerNewsFetchError``
  so ``SourceAdapter.safe_fetch()`` produces the failure envelope.
  A ``None``/malformed individual item is skipped in isolation and
  counted in ``last_fetch_stats`` (observable, never silent).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.domain.strategy import SourceType
from src.research.adapters.base import RawDiscovery, SourceAdapter

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_DISCUSSION_BASE = "https://news.ycombinator.com/item"
HN_HEADERS = {"User-Agent": "AI-Affiliate-Agents/Researcher2.0"}
HN_REQUEST_TIMEOUT_SECONDS = 10

#: How many top-story IDs to request per cycle (behavioral parity with NewsHunter).
DEFAULT_MAX_TOP_STORIES = 50

#: Freshness window: HN stories older than this are skipped (source-level filter).
MAX_AGE_HOURS = 48.0

#: Only HN "story" items are discoveries; polls/jobs/comments are not.
SUPPORTED_ITEM_TYPES = frozenset({"story"})

#: Injectable fetcher contract: URL -> parsed JSON or ``None``.
FetchJSON = Callable[[str], Optional[Any]]


class HackerNewsFetchError(RuntimeError):
    """Raised when the HN top-stories list itself cannot be retrieved."""


def default_fetch_json(url: str) -> Optional[Any]:
    """Production fetcher: HTTP GET + JSON parse; ``None`` on any failure.

    ``None`` expresses "this fetch failed" so the adapter can treat it
    as fatal (topstories) or skippable (single items). Kept lazy so that
    importing this module has no side effects.
    """
    import requests  # noqa: PLC0415 — lazy on purpose (no import-time I/O deps)

    try:
        response = requests.get(url, headers=HN_HEADERS, timeout=HN_REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except Exception:  # noqa: BLE001 — network failures become None by contract
        return None


def _iso_z(moment: datetime) -> str:
    """ISO-8601 UTC string with Z suffix (repo-wide timestamp convention)."""
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class HackerNewsAdapter(SourceAdapter):
    """Adapter for the public Hacker News Firebase API."""

    def __init__(
        self,
        fetch_json: Optional[FetchJSON] = None,
        now_fn: Optional[Callable[[], datetime]] = None,
        max_items: int = DEFAULT_MAX_TOP_STORIES,
    ) -> None:
        super().__init__()
        self._fetch_json: FetchJSON = fetch_json or default_fetch_json
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._max_items = max_items
        self.last_fetch_stats: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "hacker_news"

    @property
    def source_type(self) -> SourceType:
        return SourceType.HACKER_NEWS

    # ── fetching ──────────────────────────────────────────────────────

    def fetch(self) -> List[RawDiscovery]:
        now = self._now_fn()

        story_ids = self._fetch_json(f"{HN_API_BASE}/topstories.json")
        if story_ids is None:
            raise HackerNewsFetchError("HN topstories.json could not be retrieved")
        if not isinstance(story_ids, list):
            raise HackerNewsFetchError(
                f"HN topstories.json returned {type(story_ids).__name__}, expected list"
            )

        discoveries: List[RawDiscovery] = []
        stats: Dict[str, Any] = {"requested": 0, "kept": 0, "skipped": {}}

        def skip(reason: str) -> None:
            stats["skipped"][reason] = stats["skipped"].get(reason, 0) + 1

        for story_id in story_ids[: self._max_items]:
            stats["requested"] += 1
            item = self._fetch_json(f"{HN_API_BASE}/item/{story_id}.json")
            record = self._parse_item(story_id, item, now=now, skip=skip)
            if record is not None:
                discoveries.append(record)
                stats["kept"] += 1

        self.last_fetch_stats = stats
        return discoveries

    # ── parsing (source-level only — no classification/scoring) ───────

    def _parse_item(
        self,
        story_id: Any,
        item: Any,
        *,
        now: datetime,
        skip: Callable[[str], None],
    ) -> Optional[RawDiscovery]:
        if item is None:
            skip("unavailable")
            return None
        if not isinstance(item, dict):
            skip("malformed")
            return None
        if item.get("dead") or item.get("deleted"):
            skip("dead_or_deleted")
            return None

        item_type = item.get("type")
        if item_type not in SUPPORTED_ITEM_TYPES:
            skip("unsupported_type")
            return None

        title = str(item.get("title") or "").strip()
        if not title:
            skip("missing_title")
            return None

        time_ts = item.get("time")
        if isinstance(time_ts, bool) or not isinstance(time_ts, (int, float)) or time_ts <= 0:
            skip("missing_time")
            return None

        published = datetime.fromtimestamp(time_ts, tz=timezone.utc)
        # Future timestamps (clock skew) are clamped to age 0, not skipped.
        age_hours = max((now - published).total_seconds() / 3600.0, 0.0)
        if age_hours > MAX_AGE_HOURS:
            skip("too_old")
            return None

        resolved_id = str(item.get("id") or story_id)
        discussion_url = f"{HN_DISCUSSION_BASE}?id={resolved_id}"

        outbound = item.get("url")
        outbound_url = outbound.strip() if isinstance(outbound, str) else ""
        is_native = not outbound_url

        score = item.get("score")
        raw_score = float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None

        descendants = item.get("descendants")
        comments_count = (
            int(descendants) if isinstance(descendants, (int, float)) and not isinstance(descendants, bool) else None
        )

        return RawDiscovery(
            title=title,
            url=outbound_url or discussion_url,
            source_name="Hacker News",
            discovered_at=_iso_z(now),
            published_at=_iso_z(published),
            summary="",
            raw_score=raw_score,
            raw_score_label="hn_points",
            comments_count=comments_count,
            identifiers={"hn_item_id": resolved_id},
            metadata={
                "hn_item_url": discussion_url,
                "hn_native": is_native,
                "author": str(item.get("by") or ""),
                "age_hours": round(age_hours, 2),
                "hn_item_type": str(item_type),
            },
        )


__all__ = [
    "HackerNewsAdapter",
    "HackerNewsFetchError",
    "default_fetch_json",
    "HN_API_BASE",
    "HN_DISCUSSION_BASE",
    "MAX_AGE_HOURS",
    "DEFAULT_MAX_TOP_STORIES",
]
