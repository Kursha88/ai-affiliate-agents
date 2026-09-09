"""Deterministic candidate ranking with cluster diversity (Stage 3.2).

Produces the RANK stage of the intelligence pipeline:

    DISCOVER -> NORMALIZE -> DEDUPLICATE -> CLASSIFY -> VERIFY -> SCORE -> RANK

The Researcher returns a ranked shortlist, NOT a single winner.
Publication selection (formats, platforms, ``MIN_CONFIDENCE_FOR_SELECTION``,
``StrategicSelection``) is a later stage and must never happen here.

Composability contract:

- Inputs are already-classified and already-scored candidates. Ranking
  NEVER re-runs classification/verification/scoring and NEVER recomputes
  component weights: ``CandidateScore.total_score`` (the existing
  computed property) is the sole base rank score.
- ``CLUSTER_PRIORITY`` (editorial DATA) must never appear here — cluster
  diversity is enforced purely by a symmetric per-cluster cap. This is
  diversity control, not editorial priority. ``ai_news`` is a valid
  cluster exactly like any other: no ban, no hidden penalty, same cap.

Algorithm (deterministic, no randomness, no hidden clock):

1. Validation (whole input, fail-fast): ``limit`` must be an int >= 1;
   ``classification`` must be a ``ClassificationResult`` (TypeError,
   matching the Step 7 ``score.py`` style); ``candidate_id`` values must
   be unique (ValueError); every ``CandidateScore`` must pass the
   existing ``validate_score()`` (ValueError).
2. Partition: ``cluster is None`` -> excluded (``unclassified``, or
   ``ambiguous`` when ``ambiguous=True`` — never silently mapped to
   ``ai_news``); ``total_score < MIN_RANK_SCORE`` -> excluded
   (``below_quality_threshold``; the exact threshold value is accepted).
3. Sort eligible by ``total_score`` descending, tie-break
   ``candidate_id`` ascending. Iterate in that order and accept a
   candidate only if its cluster currently holds fewer than
   ``MAX_PER_CLUSTER`` accepted candidates (otherwise
   ``cluster_cap``) and the shortlist limit has not been reached
   (otherwise ``limit_reached``).
4. All exclusions are emitted in the same deterministic order as the
   eligible sort (``total_score`` desc, ``candidate_id`` asc), so the
   result is independent of input order.

Boundaries: no DB/network/filesystem/random/current-clock, no source
preference of any kind (provenance already lives inside
``CandidateScore.credibility``), no mutation of input objects, no
persistence, no selection decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from src.domain.strategy import CandidateScore, ContentCluster, validate_score
from src.research.classify import ClassificationResult

# ──────────────────────────────────────────────────────────────────────
# Deterministic ranking constants (test-visible).
# ──────────────────────────────────────────────────────────────────────

#: Minimum ``CandidateScore.total_score`` for the shortlist. The exact
#: value is accepted; anything below is excluded.
MIN_RANK_SCORE: float = 4.0

#: Symmetric per-cluster shortlist cap (diversity control).
MAX_PER_CLUSTER: int = 2

#: Default shortlist size.
DEFAULT_LIMIT: int = 10

# ──────────────────────────────────────────────────────────────────────
# Stable exclusion / evidence vocabulary.
# ──────────────────────────────────────────────────────────────────────

REASON_UNCLASSIFIED: str = "unclassified"
REASON_AMBIGUOUS: str = "ambiguous"
REASON_BELOW_QUALITY_THRESHOLD: str = "below_quality_threshold"
REASON_CLUSTER_CAP: str = "cluster_cap"
REASON_LIMIT_REACHED: str = "limit_reached"


# ──────────────────────────────────────────────────────────────────────
# Input / output contracts (pure, minimal, immutable)
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RankableCandidate:
    """One already-classified, already-scored candidate to rank."""

    candidate_id: str
    classification: ClassificationResult
    score: CandidateScore
    source_name: str = ""
    source_url: Optional[str] = None


@dataclass(frozen=True)
class RankedCandidate:
    """One accepted candidate with its shortlist position."""

    candidate_id: str
    rank: int  # 1-based shortlist position
    score: CandidateScore
    cluster: ContentCluster
    final_rank_score: float
    reason: str  # concise stable evidence, e.g. "ranked:ai_tools"


@dataclass(frozen=True)
class ExcludedCandidate:
    """One candidate kept out of the shortlist, with a stable reason."""

    candidate_id: str
    reason: str
    total_score: float
    cluster: Optional[ContentCluster]


@dataclass(frozen=True)
class RankingResult:
    """Outcome of one ranking pass (fully observable)."""

    ranked: Tuple[RankedCandidate, ...]
    excluded: Tuple[ExcludedCandidate, ...]
    input_count: int
    output_count: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "ranked": [
                {
                    "candidate_id": item.candidate_id,
                    "rank": item.rank,
                    "cluster": item.cluster.value,
                    "final_rank_score": item.final_rank_score,
                    "reason": item.reason,
                }
                for item in self.ranked
            ],
            "excluded": [
                {
                    "candidate_id": item.candidate_id,
                    "reason": item.reason,
                    "total_score": item.total_score,
                    "cluster": item.cluster.value if item.cluster else None,
                }
                for item in self.excluded
            ],
            "input_count": self.input_count,
            "output_count": self.output_count,
        }


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def _exclusion_sort_key(item: RankableCandidate) -> Tuple[float, str]:
    """Deterministic exclusion order: total desc, candidate_id asc."""
    return (-float(item.score.total_score), item.candidate_id)


def rank_candidates(
    candidates: Iterable[RankableCandidate],
    *,
    limit: int = DEFAULT_LIMIT,
) -> RankingResult:
    """Rank already-scored candidates into a diversity-aware shortlist.

    See the module docstring for the full algorithm and boundaries.
    Same input (in any order) produces an identical ``RankingResult``.
    """
    items = list(candidates)

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError(f"limit must be an integer >= 1, got {limit!r}")

    # Whole-input validation first: fail-fast, order-independent.
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item.classification, ClassificationResult):
            raise TypeError(
                "classification must be a ClassificationResult, got "
                f"{type(item.classification).__name__}"
            )
        if item.candidate_id in seen_ids:
            raise ValueError(f"duplicate candidate_id: {item.candidate_id!r}")
        seen_ids.add(item.candidate_id)
        validation = validate_score(item.score)
        if not validation["valid"]:
            raise ValueError(
                f"invalid CandidateScore for {item.candidate_id!r}: "
                f"{validation['issues']}"
            )

    excluded: List[Tuple[RankableCandidate, str]] = []
    eligible: List[RankableCandidate] = []

    for item in items:
        classification = item.classification
        if classification.cluster is None:
            # No silent fallback to any cluster (e.g. ai_news).
            reason = REASON_AMBIGUOUS if classification.ambiguous else REASON_UNCLASSIFIED
            excluded.append((item, reason))
            continue
        if float(item.score.total_score) < MIN_RANK_SCORE:
            excluded.append((item, REASON_BELOW_QUALITY_THRESHOLD))
            continue
        eligible.append(item)

    eligible.sort(key=_exclusion_sort_key)

    ranked: List[RankedCandidate] = []
    cluster_counts: Dict[ContentCluster, int] = {}
    for item in eligible:
        cluster = item.classification.cluster
        total = float(item.score.total_score)
        if len(ranked) >= limit:
            excluded.append((item, REASON_LIMIT_REACHED))
            continue
        if cluster_counts.get(cluster, 0) >= MAX_PER_CLUSTER:
            excluded.append((item, REASON_CLUSTER_CAP))
            continue
        cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
        ranked.append(
            RankedCandidate(
                candidate_id=item.candidate_id,
                rank=len(ranked) + 1,
                score=item.score,
                cluster=cluster,
                final_rank_score=total,
                reason=f"ranked:{cluster.value}",
            )
        )

    # Emit exclusions in the same deterministic order as the eligible
    # sort so the result never depends on input order.
    excluded.sort(key=lambda pair: _exclusion_sort_key(pair[0]))
    excluded_candidates = tuple(
        ExcludedCandidate(
            candidate_id=item.candidate_id,
            reason=reason,
            total_score=float(item.score.total_score),
            cluster=item.classification.cluster,
        )
        for item, reason in excluded
    )

    return RankingResult(
        ranked=tuple(ranked),
        excluded=excluded_candidates,
        input_count=len(items),
        output_count=len(ranked),
    )


__all__ = [
    "MIN_RANK_SCORE",
    "MAX_PER_CLUSTER",
    "DEFAULT_LIMIT",
    "REASON_UNCLASSIFIED",
    "REASON_AMBIGUOUS",
    "REASON_BELOW_QUALITY_THRESHOLD",
    "REASON_CLUSTER_CAP",
    "REASON_LIMIT_REACHED",
    "RankableCandidate",
    "RankedCandidate",
    "ExcludedCandidate",
    "RankingResult",
    "rank_candidates",
]
