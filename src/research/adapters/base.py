"""Base contract for Researcher 2.0 source adapters.

Design rules:
- Adapters are source-specific; everything downstream is source-neutral.
- Adapters return ``RawDiscovery`` records: pre-classification,
  pre-validation raw material with full source provenance. A
  ``RawDiscovery`` is deliberately NOT a ``DiscoveryCandidate`` — it
  makes no claims about cluster, verification or quality.
- Adapters must never raise out of ``fetch()`` for expected source
  failures (HTTP errors, rate limits, malformed payloads). They either
  return a list (possibly empty) or raise for genuine programming
  errors; ``safe_fetch()`` converts any exception into an isolated,
  logged failure so one broken source can never abort the cycle.
- Network clients are injected by concrete adapters (or patched in
  tests); this module performs no I/O and has no runtime side effects.
- Declaring ``name`` and ``source_type`` is mandatory per adapter —
  there is no implicit default source type.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from src.domain.strategy import SourceType


@dataclass(frozen=True)
class RawDiscovery:
    """Raw discovery record produced by an adapter (pre-classification).

    Source-neutral on purpose: no cluster, no verification, no quality
    judgment — those are later pipeline stages. ``identifiers`` carries
    source-specific canonical identities (e.g. ``github_repo`` =
    ``owner/repo``, ``hn_item_id`` = story id) that downstream dedup can
    use; ``metadata`` carries everything else (age, author, subreddit…).
    """

    title: str
    url: Optional[str]
    source_name: str
    discovered_at: str  # ISO-8601 UTC string, set by the adapter at fetch time
    published_at: Optional[str] = None  # ISO-8601 UTC string, if the source provides it
    summary: str = ""
    raw_score: Optional[float] = None  # platform-native metric value
    raw_score_label: str = ""  # what raw_score means ("hn_points", "github_stars", …)
    comments_count: Optional[int] = None
    identifiers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SourceAdapter(abc.ABC):
    """Contract for one discovery source.

    Concrete adapters implement ``fetch()`` returning zero or more
    ``RawDiscovery`` records. Expected source failures (network errors,
    rate limits, bad payloads) must be handled inside ``fetch()`` (return
    ``[]``); ``safe_fetch()`` additionally guarantees failure isolation
    for anything unexpected, recording the reason in ``last_error``.
    """

    #: Set by ``safe_fetch()`` when the adapter failed; ``None`` otherwise.
    last_error: Optional[str]

    def __init__(self) -> None:
        self.last_error = None

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique adapter name (e.g. ``"hacker_news"``)."""

    @property
    @abc.abstractmethod
    def source_type(self) -> SourceType:
        """The Stage 3.1 source type this adapter feeds — explicit, no default."""

    @abc.abstractmethod
    def fetch(self) -> List[RawDiscovery]:
        """Fetch raw discoveries from the source. Never returns ``None``."""

    def safe_fetch(self) -> List[RawDiscovery]:
        """``fetch()`` with failure isolation.

        Returns ``[]`` and populates ``last_error`` instead of raising,
        so a single broken source can never abort a research cycle.
        """
        self.last_error = None
        try:
            results = self.fetch()
        except Exception as exc:  # noqa: BLE001 — isolation boundary by contract
            self.last_error = f"{type(exc).__name__}: {exc}"
            return []
        if results is None:
            self.last_error = "adapter returned None instead of a list"
            return []
        return list(results)

    def fetch_result(self) -> "AdapterFetchResult":
        """Run ``safe_fetch()`` and wrap the outcome for the orchestrator."""
        discoveries = self.safe_fetch()
        return AdapterFetchResult(
            adapter_name=self.name,
            source_type=self.source_type,
            discoveries=tuple(discoveries),
            error=self.last_error,
        )


@dataclass(frozen=True)
class AdapterFetchResult:
    """Outcome envelope of one adapter fetch (for orchestration/logging)."""

    adapter_name: str
    source_type: SourceType
    discoveries: Tuple[RawDiscovery, ...] = ()
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


__all__ = [
    "RawDiscovery",
    "SourceAdapter",
    "AdapterFetchResult",
]
