"""SELECT-stage facade over ResearchResult (Step 14E).

One pure orchestration step:

    ResearchResult -> selected winner binding -> ContentCandidate

Composes the two existing functions without duplicating any selection
logic:

1. ``selected = select_research_result_winner(result)`` exactly once
   (Step 14C: winner binding + candidate_id consistency).
2. ``selected is None`` -> return ``None``.
3. Unpack ``processed, ranked_candidate, selection = selected``.
   ``ranked_candidate`` is intentionally UNUSED after unpacking — it is
   not inspected, not validated, and its ``candidate_id`` is not used
   again; Step 14C already resolved identity consistency.
4. ``content_candidate = build_selected_content_candidate(processed,
   selection)`` exactly once (Step 14D: projection).
5. Return that exact ``ContentCandidate`` object — never copied or
   reconstructed.

Exceptions from either callee propagate unchanged. The facade inspects
no ``ResearchResult`` internals, no candidate fields and no
``StrategicSelection`` fields — it is orchestration only.
"""

from __future__ import annotations

from src.domain.strategy import ContentCandidate
from src.research.researcher import ResearchResult
from src.research.select_result import select_research_result_winner
from src.research.content_candidate import build_selected_content_candidate


def run_select_stage(
    result: ResearchResult,
) -> ContentCandidate | None:
    """Run the SELECT stage for one ResearchResult.

    Returns the projected ``ContentCandidate`` for the selected winner,
    or ``None`` when no candidate was selected.
    """
    selected = select_research_result_winner(result)
    if selected is None:
        return None
    processed, ranked_candidate, selection = selected
    return build_selected_content_candidate(processed, selection)
