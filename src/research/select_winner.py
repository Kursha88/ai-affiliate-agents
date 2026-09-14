"""SELECT one editorial winner from an already-ranked shortlist (Step 14B).

Ranking is authoritative: ``RankingResult.ranked`` is already the
deterministic shortlist (total desc, candidate_id asc, cluster caps, limit).
This module only walks that tuple IN ITS EXISTING ORDER and returns the
FIRST candidate whose ``StrategicSelection`` (from the Step 14A selector)
is selected:

    RANK -> SELECT (per candidate) -> WINNER

It MUST NOT sort, re-rank, recompute scores, inspect discovery content,
inspect ``ProcessedCandidate``, or use AI/DB/state/network/filesystem.

Exact algorithm:

- iterate ``ranking.ranked`` in existing tuple order;
- call ``select_ranked_candidate(candidate)`` exactly once per candidate;
- on the first ``selection.selected is True`` -> immediately return
  ``(candidate, selection)`` (both by identity, no copies, no dicts,
  no new wrapper type);
- rejected selections continue to the next candidate;
- empty shortlist or no selected candidate -> ``None`` (never raise);
- selector exceptions propagate unchanged — broken candidates are never
  silently skipped.

Winner logic inspects only ``selection.selected`` — never candidate
fields directly (those belong to the Step 14A selector).
"""

from __future__ import annotations

from src.research.rank import RankingResult, RankedCandidate
from src.research.select import select_ranked_candidate
from src.domain.strategy import StrategicSelection


def select_shortlist_winner(
    ranking: RankingResult,
) -> tuple[RankedCandidate, StrategicSelection] | None:
    """Return (winner, selection) for the first selected ranked candidate.

    Preserves ``ranking.ranked`` order exactly; returns ``None`` when the
    shortlist is empty or no candidate is editorially selected.
    """
    for candidate in ranking.ranked:
        selection = select_ranked_candidate(candidate)
        if selection.selected:
            return (candidate, selection)
    return None
