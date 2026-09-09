"""Curated official RSS/Atom discovery adapter (Stage 3.2, Step 10).

Responsibility boundary:

    explicitly configured official feeds -> source-level parsing ->
    RawDiscovery[]

This adapter ONLY discovers and normalizes source data. It must NOT
classify, verify, score, rank, select or publish, and it never returns
a ``VerificationResult``. ``OfficialFeed.trusted_domain`` is NEUTRAL
curated provenance metadata; the adapter merely exposes
``trusted_primary_domains`` as future input for
``verify_provenance()`` — verification itself happens only in the
later pipeline stage, never here.

Design decisions (Stage 3.2, final):

- Feed configs are explicit and curated (``OfficialFeed``); no vendor
  domain list is hardcoded. ``trusted_domain`` is validated
  conservatively at construction: non-blank dotted hostname, no
  scheme/path/credentials, lowercased, ``www.`` normalized away;
  malformed config raises ``ValueError``.
- One adapter instance has exactly one ``source_type``
  (``OFFICIAL_BLOG`` or ``OFFICIAL_DOCS``); blogs and docs use
  separate instances.
- Network flows through an injectable ``fetch_text(url) -> str|None``;
  the production default wires ``requests`` lazily so importing this
  module performs no I/O. Tests use fakes with ZERO live network.
- Parsing uses Python stdlib XML only (``xml.etree.ElementTree``) and
  supports RSS 2.0 (``<item>``) and Atom (``<entry>``), namespace-
  tolerant via local-name matching.

Failure isolation: one failing feed never kills the others (partial
success returns records and retains failure stats); if EVERY
configured feed fails, ``fetch()`` raises ``RSSFetchError`` so
``SourceAdapter.safe_fetch()`` exposes the adapter-level failure. One
malformed entry never kills the remaining entries; skips are counted,
never silent.

In-adapter dedup (first occurrence wins, no fuzzy-title matching):

1. same feed-native entry id (guid/id) within the SAME feed;
2. fallback: same normalized URL within the SAME feed.

Cross-feed same URL is PRESERVED: different official feeds are
separate provenance records.

No pagination in Phase 1. Timestamps come from the feed only (no local
machine clock): ``published`` preferred, ``updated`` fallback,
normalized to timezone-aware UTC ISO where parseable; raw strings are
retained in metadata.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit

from src.domain.strategy import SourceType
from src.research.adapters.base import RawDiscovery, SourceAdapter
from src.research.normalize import normalize_url

OFFICIAL_RSS_HEADERS = {
    "User-Agent": "AI-Affiliate-Agents/Researcher2.0",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
}
OFFICIAL_RSS_REQUEST_TIMEOUT_SECONDS = 15

#: Conservative Phase 1 bounds (constructor-configurable).
DEFAULT_PER_FEED_LIMIT = 30
DEFAULT_MAX_RESULTS = 100

#: Conservative summary bound: long HTML bodies are truncated after
#: tag/entity stripping (deterministic, documented).
SUMMARY_MAX_CHARS = 500

#: One adapter instance feeds exactly one source type.
ALLOWED_SOURCE_TYPES = frozenset({SourceType.OFFICIAL_BLOG, SourceType.OFFICIAL_DOCS})

#: Injectable text fetcher contract: URL -> feed text or ``None``.
FetchText = Callable[[str], Optional[str]]


class RSSFetchError(RuntimeError):
    """Raised when EVERY configured feed failed (adapter-level failure)."""


def default_fetch_text(url: str) -> Optional[str]:
    """Production fetcher: HTTP GET -> response text; ``None`` on failure.

    Kept lazy so importing this module has no import-time I/O deps.
    Token/auth support (if ever needed) belongs to this client boundary,
    not to business logic.
    """
    import requests  # noqa: PLC0415 — lazy on purpose (no import-time I/O deps)

    try:
        response = requests.get(
            url, headers=OFFICIAL_RSS_HEADERS, timeout=OFFICIAL_RSS_REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return response.text
    except Exception:  # noqa: BLE001 — network failures become None by contract
        return None


def _normalize_trusted_domain(value: Any) -> str:
    """Conservatively validate/normalize one curated trusted domain.

    Accepts a non-blank dotted hostname without scheme, path,
    credentials, port or query; lowercases; strips a leading ``www.``.
    Malformed configuration raises ``ValueError`` (fail-fast, never a
    silently useless trusted set).
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"OfficialFeed.trusted_domain must be a non-blank domain, got {value!r}"
        )
    host = value.strip().lower()
    if "://" in host or any(ch in host for ch in "/:@?# "):
        raise ValueError(
            "OfficialFeed.trusted_domain must be a bare hostname "
            f"(no scheme/path/credentials), got {value!r}"
        )
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        raise ValueError(
            f"OfficialFeed.trusted_domain must be a dotted domain, got {value!r}"
        )
    return host


@dataclass(frozen=True)
class OfficialFeed:
    """One explicitly configured official feed (immutable)."""

    name: str
    feed_url: str
    trusted_domain: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                f"OfficialFeed.name must be a non-blank string, got {self.name!r}"
            )
        object.__setattr__(self, "name", self.name.strip())

        if not isinstance(self.feed_url, str) or not self.feed_url.strip():
            raise ValueError(
                f"OfficialFeed.feed_url must be a non-blank URL, got {self.feed_url!r}"
            )
        feed_url = self.feed_url.strip()
        try:
            scheme = (urlsplit(feed_url).scheme or "").lower()
        except ValueError:
            scheme = ""
        if scheme not in ("http", "https"):
            raise ValueError(
                "OfficialFeed.feed_url must be an absolute http(s) URL, "
                f"got {self.feed_url!r}"
            )
        object.__setattr__(self, "feed_url", feed_url)

        object.__setattr__(self, "trusted_domain", _normalize_trusted_domain(self.trusted_domain))


# ──────────────────────────────────────────────────────────────────────
# XML helpers (stdlib ElementTree, namespace-tolerant local names)
# ──────────────────────────────────────────────────────────────────────


def _local(tag: Any) -> str:
    """Local name of an XML tag (namespaces stripped); "" for non-tags."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _find_text(element: ET.Element, local_name: str) -> Optional[str]:
    """Text of the first direct child with the given local name.

    Collects ALL descendant text (``itertext``): real-world feeds embed
    escaped HTML or sometimes literal child elements inside
    ``description``/``content``; only descendant text is content.
    Returns ``None`` when the child is missing OR present-but-empty, so
    callers can fall back to a sibling element.
    """
    for child in element:
        if _local(child.tag) == local_name:
            text = "".join(child.itertext()).strip()
            if text:
                return text
            return None
    return None


def _feed_entries(root: ET.Element) -> Tuple[Optional[str], List[ET.Element]]:
    """Detect RSS 2.0 vs Atom and return (format, entry elements)."""
    root_local = _local(root.tag)
    if root_local == "rss":
        return "rss", [el for el in root.iter() if _local(el.tag) == "item"]
    if root_local == "feed":
        return "atom", [el for el in root.iter() if _local(el.tag) == "entry"]
    return None, []


def _entry_link(entry: ET.Element, source_format: str) -> Optional[str]:
    """Entry link: RSS ``<link>`` text; Atom ``<link href>`` with
    ``rel="alternate"`` preferred, first link as fallback."""
    if source_format == "rss":
        return _find_text(entry, "link")
    first: Optional[str] = None
    for child in entry:
        if _local(child.tag) == "link":
            href = (child.get("href") or "").strip()
            if not href:
                continue
            if first is None:
                first = href
            if child.get("rel") == "alternate":
                return href
    return first


def _entry_author(entry: ET.Element, source_format: str) -> Optional[str]:
    """Author if available: RSS ``<author>``/``dc:creator`` text; Atom
    ``<author><name>``."""
    if source_format == "atom":
        for child in entry:
            if _local(child.tag) == "author":
                name = _find_text(child, "name")
                if name:
                    return name
        return None
    return _find_text(entry, "creator") or _find_text(entry, "author")


def _strip_html(text: Any) -> str:
    """Conservatively strip a summary: remove tags, unescape entities,
    collapse whitespace, truncate to ``SUMMARY_MAX_CHARS``."""
    if not isinstance(text, str) or not text.strip():
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:SUMMARY_MAX_CHARS]


def _to_utc_iso(raw: Any) -> Optional[str]:
    """Normalize a feed timestamp to timezone-aware UTC ISO.

    Handles RFC 822 (RSS ``pubDate``) and ISO 8601 (Atom); naive values
    are assumed UTC. Unparseable input returns ``None`` (the raw string
    is retained in metadata by the caller).
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    parsed: Optional[datetime] = None
    try:
        parsed = parsedate_to_datetime(text)  # RFC 822
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            iso = text[:-1] + "+00:00" if text.endswith("Z") else text
            parsed = datetime.fromisoformat(iso)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


class OfficialRssAdapter(SourceAdapter):
    """Adapter for explicitly configured official RSS/Atom feeds."""

    def __init__(
        self,
        feeds: Iterable[OfficialFeed],
        *,
        source_type: SourceType,
        fetch_text: Optional[FetchText] = None,
        per_feed_limit: int = DEFAULT_PER_FEED_LIMIT,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> None:
        super().__init__()
        # Strict enum requirement: a raw string like "official_blog"
        # compares equal to the StrEnum member and must NOT slip through.
        if not isinstance(source_type, SourceType) or source_type not in ALLOWED_SOURCE_TYPES:
            allowed = ", ".join(sorted(st.value for st in ALLOWED_SOURCE_TYPES))
            raise ValueError(
                f"source_type must be one of ({allowed}), got {source_type!r}"
            )
        feed_tuple = tuple(feeds) if feeds is not None else ()
        if not feed_tuple:
            raise ValueError("feeds must contain at least one OfficialFeed")
        for feed in feed_tuple:
            if not isinstance(feed, OfficialFeed):
                raise ValueError(
                    f"feeds must contain only OfficialFeed instances, got {type(feed).__name__}"
                )
        self._feeds: Tuple[OfficialFeed, ...] = feed_tuple
        self._source_type = source_type
        self._fetch_text: FetchText = fetch_text or default_fetch_text
        self._validate_limits(per_feed_limit, max_results)
        self._per_feed_limit = per_feed_limit
        self._max_results = max_results
        self.last_fetch_stats: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "official_rss"

    @property
    def source_type(self) -> SourceType:
        return self._source_type

    @property
    def trusted_primary_domains(self) -> Tuple[str, ...]:
        """Trusted domains derived ONLY from the curated feed configs.

        Deduplicated in configuration order. This is future input for
        ``verify_provenance()``; the adapter itself never verifies.
        """
        seen: set[str] = set()
        ordered: List[str] = []
        for feed in self._feeds:
            if feed.trusted_domain not in seen:
                seen.add(feed.trusted_domain)
                ordered.append(feed.trusted_domain)
        return tuple(ordered)

    # ── validation ────────────────────────────────────────────────────

    @staticmethod
    def _validate_limits(per_feed_limit: int, max_results: int) -> None:
        """Positive integers only; bool is not an int here."""
        for label, value in (
            ("per_feed_limit", per_feed_limit),
            ("max_results", max_results),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer, got {value!r}")

    # ── fetching ──────────────────────────────────────────────────────

    def fetch(self) -> List[RawDiscovery]:
        stats: Dict[str, Any] = {
            "requested_feeds": len(self._feeds),
            "failed_feeds": 0,
            "feed_errors": {},
            "parsed": 0,
            "skipped": {},
            "kept": 0,
        }

        def skip(reason: str) -> None:
            stats["skipped"][reason] = stats["skipped"].get(reason, 0) + 1

        discoveries: List[RawDiscovery] = []
        # Same-feed identity only: (feed name, entry id) and
        # (feed name, normalized URL). Cross-feed same URL is preserved.
        id_index: Dict[Tuple[str, str], int] = {}
        url_index: Dict[Tuple[str, str], int] = {}

        for feed in self._feeds:
            text = self._fetch_text(feed.feed_url)
            if text is None:
                stats["failed_feeds"] += 1
                stats["feed_errors"][feed.name] = "fetch_failed"
                continue
            try:
                root = ET.fromstring(text)
            except ET.ParseError:
                stats["failed_feeds"] += 1
                stats["feed_errors"][feed.name] = "malformed_feed_xml"
                continue

            source_format, entries = _feed_entries(root)
            if source_format is None:
                stats["failed_feeds"] += 1
                stats["feed_errors"][feed.name] = "unsupported_feed_format"
                continue

            for entry in entries[: self._per_feed_limit]:
                if len(discoveries) >= self._max_results:
                    break  # stop as soon as the overall limit is reached
                record = self._parse_entry(
                    entry, feed=feed, source_format=source_format, skip=skip
                )
                if record is None:
                    continue

                stats["parsed"] += 1
                entry_id = record.identifiers.get("rss_entry_id")
                normalized = normalize_url(record.url)

                position: Optional[int] = None
                if entry_id is not None:
                    position = id_index.get((feed.name, entry_id))
                if position is None and normalized is not None:
                    position = url_index.get((feed.name, normalized))

                if position is not None:
                    continue  # duplicate within this feed; first wins

                if entry_id is not None:
                    id_index[(feed.name, entry_id)] = len(discoveries)
                if normalized is not None:
                    url_index[(feed.name, normalized)] = len(discoveries)
                discoveries.append(record)
                stats["kept"] += 1

            if len(discoveries) >= self._max_results:
                break

        stats["kept"] = len(discoveries)
        self.last_fetch_stats = stats
        if stats["failed_feeds"] == len(self._feeds):
            raise RSSFetchError(f"all {len(self._feeds)} configured feeds failed")
        return discoveries

    # ── parsing (source-level only — no classification/verification) ──

    def _parse_entry(
        self,
        entry: Any,
        *,
        feed: OfficialFeed,
        source_format: str,
        skip: Callable[[str], None],
    ) -> Optional[RawDiscovery]:
        if entry is None or not isinstance(getattr(entry, "tag", None), str):
            skip("malformed_entry")
            return None

        title = _find_text(entry, "title")
        if not title:
            skip("missing_title")
            return None

        link = _entry_link(entry, source_format)
        if not link or normalize_url(link) is None:
            skip("missing_or_invalid_url")
            return None

        if source_format == "rss":
            raw_summary = _find_text(entry, "description")
            published_raw = _find_text(entry, "pubDate")
            entry_id = _find_text(entry, "guid")
        else:
            raw_summary = _find_text(entry, "summary") or _find_text(entry, "content")
            published_raw = _find_text(entry, "published")
            entry_id = _find_text(entry, "id")
        updated_raw = _find_text(entry, "updated")

        published_at = _to_utc_iso(published_raw)
        if published_at is None:
            published_at = _to_utc_iso(updated_raw)  # documented fallback

        return RawDiscovery(
            title=title,
            url=link,
            source_name=feed.name,
            discovered_at=published_at or "",
            published_at=published_at,
            summary=_strip_html(raw_summary),
            raw_score=None,
            raw_score_label=None,
            comments_count=None,
            identifiers={"rss_entry_id": entry_id} if entry_id else {},
            metadata={
                "feed_name": feed.name,
                "feed_url": feed.feed_url,
                "trusted_domain": feed.trusted_domain,
                "entry_id": entry_id,
                "published_raw": published_raw,
                "updated_raw": updated_raw,
                "author": _entry_author(entry, source_format),
                "source_format": source_format,
            },
        )


__all__ = [
    "OfficialFeed",
    "OfficialRssAdapter",
    "RSSFetchError",
    "default_fetch_text",
    "OFFICIAL_RSS_HEADERS",
    "ALLOWED_SOURCE_TYPES",
    "DEFAULT_PER_FEED_LIMIT",
    "DEFAULT_MAX_RESULTS",
    "SUMMARY_MAX_CHARS",
]
