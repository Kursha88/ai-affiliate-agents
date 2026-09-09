"""Researcher 2.0 orchestration (Stage 3.2, Step 11).

Composes the existing Researcher 2.0 stages into one deterministic run:

    SourceAdapter.safe_fetch() -> collect RawDiscovery -> deduplicate()
    -> classify() -> verify_provenance() -> score_candidate()
    -> rank_candidates()

The Researcher returns a ranked shortlist plus fully observable stage
results. It must NOT publish, generate copy, choose content formats,
create ``StrategicSelection``, modify any DB or ``topic_history.json``,
or call the legacy NewsHunter/Strategist agents.

Design decisions (Stage 3.2, final):

- Adapters are injected explicitly; no adapter is constructed here and
  no environment variables are read. Tests stay fully in-memory.
- ``run()`` requires ``now`` — there is no hidden current clock.
- Source type comes from ``adapter.source_type`` for every record that
  adapter produced; it is never inferred from URLs.
- Candidate IDs are deterministic and namespaced (strong identity
  precedence: usable source-native identifiers -> canonical URL ->
  normalized title + source_name), derived via SHA-256. No random
  UUIDs. Duplicate generated IDs raise ``ValueError`` — silently
  overwriting provenance is never acceptable.
- Deduplication is the existing ``deduplicate()`` run ONCE over the
  combined raw pool; its cross-source provenance rules stay
  authoritative. No new dedup logic here.
- Classification and verification run exactly once per deduplicated
  record; unclassified candidates are retained (ranking excludes them
  via the existing ``rank_candidates`` contract). Trusted domains are
  the caller-supplied collection plus, for ``OfficialRssAdapter``
  instances, their curated ``trusted_primary_domains`` — combined and
  deduplicated deterministically. No vendor domains are hardcoded.
- Scoring calls the existing ``score_candidate()`` exactly once. A
  DISPUTED/REJECTED verification raises ``ValueError`` inside
  ``score_candidate()`` by design; the researcher handles that
  intentionally: the candidate is excluded from scoring/ranking with a
  stable reason (``verification_disputed`` / ``verification_rejected``),
  stays observable in the processing results, and never crashes the
  run. An unexpected scoring ``ValueError`` is recorded as
  ``scoring_error``. No score is ever fabricated and ``score.py`` is
  not modified.
- Ranking feeds only successfully scored candidates into the existing
  ``rank_candidates()``. No re-ranking, no ``CLUSTER_PRIORITY``, no
  source bonuses, no selection decisions.
- If every adapter fails, the result is a valid empty ``ResearchResult``
  with adapter errors — external source failures must not raise.
  An adapter returning zero records successfully is success, not
  failure.

Order/determinism: adapters execute in constructor order; the combined
input preserves adapter order then per-adapter record order; every
downstream stage is deterministic; a repeated run with the same adapter
outputs and the same ``now`` produces an equal ``ResearchResult``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Collection, Dict, List, Optional, Sequence, Tuple

from src.domain.strategy import (
    CandidateScore,
    SourceType,
    VerificationResult,
    VerificationStatus,
)
from src.research.adapters.base import RawDiscovery, SourceAdapter
from src.research.adapters.rss import OfficialRssAdapter
from src.research.classify import ClassificationResult, classify
from src.research.dedup import deduplicate
from src.research.normalize import normalize_title, url_identity
from src.research.rank import (
    DEFAULT_LIMIT,
    RankableCandidate,
    RankingResult,
    rank_candidates,
)
from src.research.score import score_candidate
from src.research.verify import verify_provenance

# ──────────────────────────────────────────────────────────────────────
# Stable processing-exclusion reasons (observability vocabulary).
# ──────────────────────────────────────────────────────────────────────

EXCLUSION_VERIFICATION_DISPUTED: str = "verification_disputed"
EXCLUSION_VERIFICATION_REJECTED: str = "verification_rejected"
EXCLUSION_SCORING_ERROR: str = "scoring_error"


# ──────────────────────────────────────────────────────────────────────
# Result contracts (immutable, observable)
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AdapterOutcome:
    """Observable outcome of one adapter's ``safe_fetch()``."""

    adapter_name: str
    source_type: SourceType
    ok: bool
    record_count: int
    error: Optional[str] = None


@dataclass(frozen=True)
class ProcessedCandidate:
    """One deduplicated discovery carried through all stages."""

    candidate_id: str
    discovery: RawDiscovery
    source_type: SourceType
    classification: ClassificationResult
    verification: VerificationResult
    score: Optional[CandidateScore] = None
    processing_exclusion: Optional[str] = None  # stable reason when unscoreable


@dataclass(frozen=True)
class ResearchResult:
    """Outcome of one Researcher run (fully observable)."""

    ranked: RankingResult
    candidates: Tuple[ProcessedCandidate, ...]
    adapter_results: Tuple[AdapterOutcome, ...]
    input_count: int
    deduplicated_count: int
    classified_count: int
    verified_count: int
    scored_count: int
    trusted_primary_domains: Tuple[str, ...] = ()

    @property
    def adapter_errors(self) -> Tuple[AdapterOutcome, ...]:
        """Adapters that failed, in execution order."""
        return tuple(outcome for outcome in self.adapter_results if not outcome.ok)


# ──────────────────────────────────────────────────────────────────────
# Deterministic candidate identity
# ──────────────────────────────────────────────────────────────────────


def _usable_identifiers(discovery: RawDiscovery) -> List[Tuple[str, str]]:
    """Usable namespaced native identifiers, in declaration order.

    Same conservative shape as dedup.py: blank/generic keys and
    non-string values are ignored; the source namespace travels with
    the value so unrelated sources' IDs can never collide.
    """
    ignored_keys = {"id", "key", "uid"}
    usable: List[Tuple[str, str]] = []
    for key, raw_value in (discovery.identifiers or {}).items():
        if not isinstance(key, str):
            continue
        namespace = key.strip()
        if not namespace or namespace.lower() in ignored_keys:
            continue
        if isinstance(raw_value, bool) or not isinstance(raw_value, str):
            continue
        value = raw_value.strip()
        if not value:
            continue
        usable.append((namespace, value))
    return usable


def _identity_components(
    discovery: RawDiscovery, source_type: SourceType
) -> Tuple[str, str]:
    """Strong identity precedence -> (kind, value).

    1. usable source-native identifiers (namespaced with the source);
    2. canonical URL identity;
    3. conservative normalized title + source_name fallback.
    """
    identifiers = _usable_identifiers(discovery)
    if identifiers:
        parts = ";".join(f"{namespace}={value}" for namespace, value in identifiers)
        return "native", f"{source_type.value}:{parts}"

    canonical_url = url_identity(discovery.url)
    if canonical_url is not None:
        return "url", f"{source_type.value}:{canonical_url}"

    title_key = normalize_title(discovery.title)
    source_key = (discovery.source_name or "").strip()
    if title_key and source_key:
        return "title", f"{source_type.value}:{source_key}:{title_key}"

    # Last resort (should not occur for adapter-produced records):
    # still deterministic, namespaced, and based on the raw content.
    return "raw", f"{source_type.value}:{discovery.title}:{discovery.url or ''}"


def candidate_id_for(
    discovery: RawDiscovery, source_type: SourceType
) -> str:
    """Deterministic namespaced candidate ID (SHA-256-derived).

    Stable for the same discovery content: the identity precedence is
    applied first, then hashed. No random UUIDs.
    """
    kind, value = _identity_components(discovery, source_type)
    digest = hashlib.sha256(f"{kind}:{value}".encode("utf-8")).hexdigest()
    return f"cand_{digest}"


def _combine_trusted_domains(
    configured: Collection[str],
    adapters: Sequence[SourceAdapter],
) -> Tuple[str, ...]:
    """Deterministic, deduplicated trusted-domain combination.

    Caller-supplied domains first (given order), then each RSS adapter's
    curated domains in adapter order. Malformed/non-string entries are
    dropped; RSS-curated entries are already normalized by the adapter.
    """
    seen: set[str] = set()
    ordered: List[str] = []
    for domain in list(configured) + [
        domain
        for adapter in adapters
        if isinstance(adapter, OfficialRssAdapter)
        for domain in adapter.trusted_primary_domains
    ]:
        if isinstance(domain, str):
            host = domain.strip().lower()
            if host and host not in seen:
                seen.add(host)
                ordered.append(host)
    return tuple(ordered)


# ──────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────


class Researcher:
    """Orchestrates discover -> dedup -> classify -> verify -> score -> rank."""

    def __init__(
        self,
        adapters: Sequence[SourceAdapter],
        *,
        trusted_primary_domains: Collection[str] = (),
    ) -> None:
        adapter_list = list(adapters)
        for adapter in adapter_list:
            if not isinstance(adapter, SourceAdapter):
                raise ValueError(
                    "adapters must contain only SourceAdapter instances, got "
                    f"{type(adapter).__name__}"
                )
        self._adapters: Tuple[SourceAdapter, ...] = tuple(adapter_list)
        self._trusted_primary_domains: Tuple[str, ...] = _combine_trusted_domains(
            trusted_primary_domains, self._adapters
        )

    @property
    def trusted_primary_domains(self) -> Tuple[str, ...]:
        """Combined trusted domains (configured + RSS-curated), deterministic."""
        return self._trusted_primary_domains

    def run(
        self,
        *,
        now: datetime,
        limit: int = DEFAULT_LIMIT,
    ) -> ResearchResult:
        """Execute one deterministic research cycle.

        ``now`` is REQUIRED (no hidden clock); ``limit`` is forwarded to
        ``rank_candidates``. See the module docstring for stage rules.
        """
        if not isinstance(now, datetime):
            raise TypeError(f"now must be a datetime, got {type(now).__name__}")

        # ── Stage 1: DISCOVER (adapter order, safe_fetch per adapter) ────
        adapter_results: List[AdapterOutcome] = []
        pool: List[Tuple[RawDiscovery, SourceType]] = []
        for adapter in self._adapters:
            discoveries = adapter.safe_fetch()
            ok = adapter.last_error is None
            adapter_results.append(
                AdapterOutcome(
                    adapter_name=adapter.name,
                    source_type=adapter.source_type,
                    ok=ok,
                    record_count=len(discoveries),
                    error=adapter.last_error,
                )
            )
            source_type = adapter.source_type
            for discovery in discoveries:
                pool.append((discovery, source_type))

        input_count = len(pool)

        # ── Stage 2: DEDUPLICATE (existing dedup, once, whole pool) ──────
        dedup_result = deduplicate(discovery for discovery, _ in pool)
        deduplicated: List[RawDiscovery] = list(dedup_result.items)

        # Restore each deduplicated record's source type from the pool
        # (same object identity; dedup never reconstructs records).
        source_type_by_identity: Dict[int, SourceType] = {
            id(discovery): source_type for discovery, source_type in pool
        }

        # ── Stages 3-5: CLASSIFY -> VERIFY -> SCORE (once each) ──────────
        trusted = self._trusted_primary_domains
        processed: List[ProcessedCandidate] = []
        seen_ids: set[str] = set()
        classified_count = 0
        verified_count = 0
        scored_count = 0

        for discovery in deduplicated:
            source_type = source_type_by_identity[id(discovery)]

            candidate_id = candidate_id_for(discovery, source_type)
            if candidate_id in seen_ids:
                raise ValueError(
                    f"duplicate generated candidate_id: {candidate_id}"
                )
            seen_ids.add(candidate_id)

            # Classification: exactly once, never discarded early.
            classification = classify(discovery, source_type)
            classified_count += 1

            # Provenance verification: exactly once, trusted domains only.
            verification = verify_provenance(
                discovery, source_type, trusted_primary_domains=trusted
            )
            verified_count += 1

            # Scoring: exactly once; intentional handling of DISPUTED /
            # REJECTED / unexpected scoring errors — observable, never fatal.
            score: Optional[CandidateScore] = None
            exclusion: Optional[str] = None
            if verification.verification_status == VerificationStatus.DISPUTED:
                exclusion = EXCLUSION_VERIFICATION_DISPUTED
            elif verification.verification_status == VerificationStatus.REJECTED:
                exclusion = EXCLUSION_VERIFICATION_REJECTED
            else:
                try:
                    score = score_candidate(
                        discovery,
                        classification=classification,
                        verification=verification,
                        now=now,
                        source_type=source_type,
                    )
                except ValueError:
                    exclusion = EXCLUSION_SCORING_ERROR
            if score is not None:
                scored_count += 1

            processed.append(
                ProcessedCandidate(
                    candidate_id=candidate_id,
                    discovery=discovery,
                    source_type=source_type,
                    classification=classification,
                    verification=verification,
                    score=score,
                    processing_exclusion=exclusion,
                )
            )

        # ── Stage 6: RANK (existing rank_candidates, scored only) ────────
        rankable = [
            RankableCandidate(
                candidate_id=item.candidate_id,
                classification=item.classification,
                score=item.score,  # type: ignore[arg-type] — scored only
                source_name=item.discovery.source_name,
                source_url=item.discovery.url,
            )
            for item in processed
            if item.score is not None
        ]
        ranked = rank_candidates(rankable, limit=limit)

        return ResearchResult(
            ranked=ranked,
            candidates=tuple(processed),
            adapter_results=tuple(adapter_results),
            input_count=input_count,
            deduplicated_count=len(deduplicated),
            classified_count=classified_count,
            verified_count=verified_count,
            scored_count=scored_count,
            trusted_primary_domains=trusted,
        )


__all__ = [
    "EXCLUSION_VERIFICATION_DISPUTED",
    "EXCLUSION_VERIFICATION_REJECTED",
    "EXCLUSION_SCORING_ERROR",
    "AdapterOutcome",
    "ProcessedCandidate",
    "ResearchResult",
    "Researcher",
    "candidate_id_for",
    "DEFAULT_LIMIT",
]
