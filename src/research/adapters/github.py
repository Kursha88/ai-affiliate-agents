"""GitHub source adapter for Researcher 2.0 (Phase 1).

Responsibility boundary (Stage 3.2):

    GitHub public REST search -> source-level parsing/filtering ->
    RawDiscovery[]

This adapter ONLY discovers and normalizes source data. It must NOT
classify, verify, score, rank, select or publish. The only filtering is
source-level hygiene (malformed payload, missing identity, archived,
fork, private/unavailable) — there is deliberately NO star-count
threshold (low-star repos may still be novel) and NO AI keyword
classification here.

License metadata is retained as NEUTRAL metadata only. A public GitHub
repository is not automatically open source, and nothing here infers
free availability, product quality or an AI cluster.

Search design:

- Phase 1 uses the public repository search API (no paid API). A small
  explicit default query set (``DEFAULT_SEARCH_QUERIES``) covers the
  editorial clusters; queries are module-level and test-visible.
- The search client is injectable (``fetch_json`` callable) so unit
  tests use ZERO live network. The production default wires
  ``requests`` lazily. An optional token can be supplied through the
  client boundary later; the adapter works conceptually without one and
  never reads environment variables inside business logic.

Identity and in-adapter dedup:

- The same repository may surface in several search queries. Records
  deduplicate ONLY by strong native identity: the numeric GitHub repo
  id first (``identifiers["github_repo_id"]``), falling back to the
  explicit ``owner/repo`` identity (``identifiers["github_repo"]``).
  First occurrence wins; all discovery queries that matched a kept repo
  are preserved in ``metadata["matched_queries"]``. No fuzzy title dedup.

Failure isolation:

- One failing query must not kill the others. Partial success returns
  the successful discoveries and retains concise failure stats
  (``last_fetch_stats``), mirroring the HN adapter's observability
  contract. If EVERY query fails, ``fetch()`` raises
  ``GitHubFetchError`` so ``SourceAdapter.safe_fetch()`` exposes the
  adapter-level failure. Nothing is silently swallowed.

Time handling: GitHub ISO timestamps are timezone-aware ISO UTC values
passed through (``Z`` normalized to ``+00:00`` offset form); no local
machine clock, no ``datetime.now()``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote_plus

from src.domain.strategy import SourceType
from src.research.adapters.base import RawDiscovery, SourceAdapter

GITHUB_API_BASE = "https://api.github.com"
GITHUB_HEADERS = {
    "User-Agent": "AI-Affiliate-Agents/Researcher2.0",
    "Accept": "application/vnd.github+json",
}
GITHUB_REQUEST_TIMEOUT_SECONDS = 15

#: Small explicit Phase 1 query set (module-level, test-visible).
DEFAULT_SEARCH_QUERIES: tuple[str, ...] = (
    "AI coding agent",
    "vibe coding",
    "LLM agent",
    "AI automation",
    "AI developer tool",
    "MCP server",
    "self hosted AI",
)

#: Conservative Phase 1 bounds (constructor-configurable).
DEFAULT_PER_QUERY_LIMIT = 20
DEFAULT_MAX_RESULTS = 50

#: Injectable fetcher contract: URL -> parsed JSON or ``None``.
FetchJSON = Callable[[str], Optional[Any]]


class GitHubFetchError(RuntimeError):
    """Raised when EVERY search query failed (adapter-level failure)."""


def _normalize_iso_utc(value: Any) -> Optional[str]:
    """Pass GitHub ISO timestamps through as timezone-aware ISO UTC.

    GitHub returns ``...Z``; this normalizes the ``Z`` suffix to the
    ``+00:00`` offset form (repo-wide ISO convention) and keeps the
    instant untouched. Returns ``None`` for missing/invalid input.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        from datetime import datetime  # lazy: stdlib only, no I/O

        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None  # GitHub timestamps are always offset-qualified
    return parsed.isoformat()


def default_fetch_json(url: str) -> Optional[Any]:
    """Production fetcher: HTTP GET + JSON parse; ``None`` on failure.

    Kept lazy so importing this module performs no I/O and has no
    import-time network dependencies. Token support (if supplied later)
    belongs to this client boundary, not to the adapter's business
    logic.
    """
    import requests  # noqa: PLC0415 — lazy on purpose (no import-time I/O deps)

    try:
        response = requests.get(
            url, headers=GITHUB_HEADERS, timeout=GITHUB_REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        return response.json()
    except Exception:  # noqa: BLE001 — network failures become None by contract
        return None


class GitHubAdapter(SourceAdapter):
    """Adapter for the GitHub public repository search API."""

    def __init__(
        self,
        fetch_json: Optional[FetchJSON] = None,
        *,
        queries: Optional[tuple[str, ...]] = None,
        per_query_limit: int = DEFAULT_PER_QUERY_LIMIT,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> None:
        super().__init__()
        self._fetch_json: FetchJSON = fetch_json or default_fetch_json
        self._queries = tuple(queries) if queries is not None else DEFAULT_SEARCH_QUERIES
        self._validate_queries(self._queries)
        self._validate_limits(per_query_limit, max_results)
        self._per_query_limit = per_query_limit
        self._max_results = max_results
        self.last_fetch_stats: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "github"

    @property
    def source_type(self) -> SourceType:
        return SourceType.GITHUB

    # ── validation ────────────────────────────────────────────────────

    @staticmethod
    def _validate_limits(per_query_limit: int, max_results: int) -> None:
        """Positive integers only; bool is not an int here."""
        for label, value in (
            ("per_query_limit", per_query_limit),
            ("max_results", max_results),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer, got {value!r}")

    @staticmethod
    def _validate_queries(queries: tuple[str, ...]) -> None:
        """At least one non-blank query — an empty set is a misconfiguration,
        not an empty result."""
        if not queries:
            raise ValueError("queries must contain at least one search query")
        for query in queries:
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f"invalid search query: {query!r}")

    # ── fetching ──────────────────────────────────────────────────────

    def fetch(self) -> List[RawDiscovery]:
        stats: Dict[str, Any] = {
            "requested_queries": len(self._queries),
            "failed_queries": 0,
            "query_errors": {},
            "parsed": 0,
            "skipped": {},
            "kept": 0,
        }

        def skip(reason: str) -> None:
            stats["skipped"][reason] = stats["skipped"].get(reason, 0) + 1

        discoveries: List[RawDiscovery] = []
        # Strongest identity first: numeric repo id, fallback owner/repo.
        # Values are indexes into ``discoveries`` (first occurrence wins).
        id_index: Dict[str, int] = {}
        name_index: Dict[str, int] = {}

        for query in self._queries:
            url = (
                f"{GITHUB_API_BASE}/search/repositories"
                f"?q={quote_plus(query)}&per_page={self._per_query_limit}"
            )
            payload = self._fetch_json(url)
            if payload is None:
                stats["failed_queries"] += 1
                stats["query_errors"][query] = "fetch_failed"
                continue
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                stats["failed_queries"] += 1
                stats["query_errors"][query] = "malformed_search_payload"
                continue

            for item in payload["items"][: self._per_query_limit]:
                if len(discoveries) >= self._max_results:
                    break  # stop as soon as the overall limit is reached
                record = self._parse_item(item, query=query, skip=skip)
                if record is None:
                    continue

                stats["parsed"] += 1
                repo_id = record.identifiers["github_repo_id"]
                repo_name = record.identifiers["github_repo"]

                position = id_index.get(repo_id)
                if position is None:
                    position = name_index.get(repo_name)

                if position is None:
                    id_index[repo_id] = len(discoveries)
                    name_index[repo_name] = len(discoveries)
                    discoveries.append(record)
                    stats["kept"] += 1
                    continue

                # Duplicate repo within this fetch: merge the new query
                # into the kept record's matched_queries. Records are
                # frozen, so the kept record is rebuilt (not mutated).
                kept = discoveries[position]
                if query not in kept.metadata["matched_queries"]:
                    merged = {
                        **kept.metadata,
                        "matched_queries": kept.metadata["matched_queries"] + (query,),
                    }
                    discoveries[position] = replace(kept, metadata=merged)

            if len(discoveries) >= self._max_results:
                break

        stats["kept"] = len(discoveries)
        self.last_fetch_stats = stats
        if stats["failed_queries"] == len(self._queries):
            raise GitHubFetchError(
                f"all {len(self._queries)} GitHub search queries failed"
            )
        return discoveries

    # ── parsing (source-level only — no classification/verification) ──

    def _parse_item(
        self,
        item: Any,
        *,
        query: str,
        skip: Callable[[str], None],
    ) -> Optional[RawDiscovery]:
        if not isinstance(item, dict):
            skip("malformed_payload")
            return None

        repo_id = item.get("id")
        if isinstance(repo_id, bool) or not isinstance(repo_id, int) or repo_id <= 0:
            skip("missing_repo_id")
            return None

        full_name = item.get("full_name")
        if not isinstance(full_name, str) or not full_name.strip():
            skip("missing_full_name")
            return None
        full_name = full_name.strip()

        html_url = item.get("html_url")
        if not isinstance(html_url, str) or not html_url.strip():
            skip("missing_or_invalid_url")
            return None
        html_url = html_url.strip()
        # The discovery URL must be the canonical repository URL
        # (https://github.com/<owner>/<repo>), not an arbitrary string.
        if not html_url.startswith("https://github.com/"):
            skip("missing_or_invalid_url")
            return None

        if item.get("archived") is True:
            skip("archived")
            return None
        if item.get("fork") is True:
            skip("fork")
            return None
        visibility = item.get("visibility")
        if visibility is not None and visibility != "public":
            skip("non_public")
            return None

        full_name_str = str(full_name)
        if "/" not in full_name_str:
            skip("missing_full_name")
            return None
        owner, _, repo_name = full_name_str.partition("/")

        stars = item.get("stargazers_count")
        raw_score = (
            float(stars)
            if isinstance(stars, (int, float)) and not isinstance(stars, bool) and stars >= 0
            else None
        )

        description = item.get("description")
        summary = description.strip() if isinstance(description, str) else ""

        topics = item.get("topics")
        topics_tuple = (
            tuple(str(topic) for topic in topics if isinstance(topic, str))
            if isinstance(topics, list)
            else ()
        )

        license_info = item.get("license")
        if isinstance(license_info, dict):
            license_key = license_info.get("key")
            license_name = license_info.get("name")
            license_meta: Dict[str, Any] = {
                "license_key": str(license_key) if isinstance(license_key, str) else None,
                "license_name": str(license_name) if isinstance(license_name, str) else None,
            }
        else:
            license_meta = {"license_key": None, "license_name": None}

        metadata: Dict[str, Any] = {
            "owner": owner,
            "repo_name": repo_name,
            "full_name": full_name_str,
            "stars": stars if isinstance(stars, (int, float)) and not isinstance(stars, bool) else None,
            "forks": item.get("forks_count"),
            "watchers": item.get("watchers_count"),
            "open_issues_count": item.get("open_issues_count"),
            "language": item.get("language"),
            "topics": topics_tuple,
            "archived": item.get("archived") is True,
            "fork": item.get("fork") is True,
            "pushed_at": _normalize_iso_utc(item.get("pushed_at")),
            "updated_at": _normalize_iso_utc(item.get("updated_at")),
            "created_at": _normalize_iso_utc(item.get("created_at")),
            "default_branch": item.get("default_branch"),
            "homepage": item.get("homepage"),
            "visibility": visibility if isinstance(visibility, str) else None,
            "discovery_query": query,
            "matched_queries": (query,),
            # Neutral license metadata only — never a free/open signal.
            **license_meta,
        }

        # Freshness signal: pushed_at is preferred (last real code push);
        # updated_at (any repo metadata change) is the documented fallback.
        published_at = (
            metadata["pushed_at"] or metadata["updated_at"]
        )

        # Title: full_name, with a concise description appended when one
        # exists (kept short — the full text lives in summary).
        title = full_name_str
        if summary:
            concise = summary.split(". ")[0].strip()
            title = f"{full_name_str}: {concise}"[:200]

        return RawDiscovery(
            title=title,
            url=html_url,
            source_name="github",
            # No local clock: freshness chain pushed_at -> updated_at ->
            # created_at; empty string only if GitHub sent nothing usable.
            discovered_at=published_at or metadata["created_at"] or "",
            published_at=published_at,
            summary=summary,
            raw_score=raw_score,
            raw_score_label="github_stars",
            comments_count=None,  # forks/issues are never misused as comments
            identifiers={
                "github_repo": full_name_str.lower(),
                "github_repo_id": str(repo_id),
            },
            metadata=metadata,
        )


__all__ = [
    "GitHubAdapter",
    "GitHubFetchError",
    "default_fetch_json",
    "GITHUB_API_BASE",
    "GITHUB_HEADERS",
    "DEFAULT_SEARCH_QUERIES",
    "DEFAULT_PER_QUERY_LIMIT",
    "DEFAULT_MAX_RESULTS",
]
