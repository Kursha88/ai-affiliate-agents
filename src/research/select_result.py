"""Bind the SELECT-stage winner back to its ProcessedCandidate (Step 14C).

Connects the winner chosen by ``select_shortlist_winner()`` (Step 14B) to
the corresponding ``ProcessedCandidate`` inside an existing
``ResearchResult``:

    ResearchResult.ranked -> winner -> candidate_id lookup
        in ResearchResult.candidates

``select_shortlist_winner()`` is authoritative: this function MUST NOT
call ``select_ranked_candidate`` directly, select another candidate,
retry selection, inspect ``selection.selected``, sort, re-rank, re-score,
re-classify or re-verify. It performs ONLY the winner lookup and the
``candidate_id`` consistency check.

Exact algorithm:

1. ``winner = select_shortlist_winner(result.ranked)`` exactly once
   (exceptions propagate unchanged).
2. ``winner is None`` -> return ``None``.
3. Unpack ``ranked_candidate, selection = winner``.
4. Match ``ProcessedCandidate`` objects where
   ``processed.candidate_id == ranked_candidate.candidate_id``.
5. Zero matches -> ``ValueError("selected ranked candidate missing from
   processed candidates")``.
6. More than one match -> ``ValueError("duplicate processed
   candidate_id")``.
7. Exactly one match -> return ``(processed_candidate,
   ranked_candidate, selection)`` — all three BY IDENTITY, never copied,
   reconstructed, converted or mutated.

Field access is restricted to ``result.ranked``, ``result.candidates``,
``ranked_candidate.candidate_id`` and ``processed.candidate_id`` — never
discovery content, classification, verification, scores, counts or
adapter results. No ``ContentCandidate`` mapping happens here (a later
step).
"""

from __future__ import annotations

from src.domain.strategy import StrategicSelection
from src.research.rank import RankedCandidate
from src.research.researcher import ProcessedCandidate, ResearchResult
from src.research.select_winner import select_shortlist_winner


def select_research_result_winner(
    result: ResearchResult,
) -> tuple[ProcessedCandidate, RankedCandidate, StrategicSelection] | None:
    """Bind the shortlist winner to its processed research candidate.

    Returns ``None`` when no winner exists; raises ``ValueError`` on
    candidate_id inconsistency between ranked and processed candidates.
    """
    winner = select_shortlist_winner(result.ranked)
    if winner is None:
        return None
    ranked_candidate, selection = winner

    matches = [
        processed
        for processed in result.candidates
        if processed.candidate_id == ranked_candidate.candidate_id
    ]
    if not matches:
        raise ValueError(
            "selected ranked candidate missing from processed candidates"
        )
    if len(matches) > 1:
        raise ValueError("duplicate processed candidate_id")

    processed_candidate = matches[0]
    return (processed_candidate, ranked_candidate, selection)
