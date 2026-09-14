"""Validated ContentCandidate → StrategistInput boundary (Stage 15, Step 15B).

FAIL-CLOSED boundary: it proves a selected ``ContentCandidate`` is safe and
complete enough to enter Strategist 2.0, and makes NO strategy decision of
its own. It only validates the SELECT invariants listed below, in the exact
order given — validation order is part of the contract:

1. ``content_candidate.stage`` is ``CandidateStage.SELECTED``
2. ``content_candidate.selection`` is not None
3. (bind) ``selection = content_candidate.selection``
4. ``selection.selected`` is True
5. ``selection.recommended_format`` is not None
6. ``selection.target_platforms`` is non-empty
7. ``content_candidate.candidate.content_cluster`` is not None
8. all checks pass → ``StrategistInput(content_candidate=content_candidate)``

Strict field access — the function reads ONLY:

    content_candidate.stage
    content_candidate.selection
    content_candidate.candidate.content_cluster
    selection.selected
    selection.recommended_format
    selection.target_platforms

and deliberately never reads ``selection_reason``, ``research_required``,
``experiment_required``, ``score``, ``verification`` or ``content_id``:
those may legitimately hold either value and require no boundary check.
No type coercion, no mutation, no try/except, no defaults.
"""

from src.domain.strategist import StrategistInput
from src.domain.strategy import (
    CandidateStage,
    ContentCandidate,
)

__all__ = ["build_strategist_input"]

_ERROR_STAGE = "content candidate is not at selected stage"
_ERROR_MISSING_SELECTION = "content candidate missing strategic selection"
_ERROR_NOT_SELECTED = "strategic selection is not selected"
_ERROR_MISSING_FORMAT = "strategic selection missing recommended format"
_ERROR_MISSING_PLATFORMS = "strategic selection missing target platforms"
_ERROR_MISSING_CLUSTER = "content candidate missing content cluster"


def build_strategist_input(
    content_candidate: ContentCandidate,
) -> StrategistInput:
    """Validate SELECT-owned state and bind the candidate for Strategist 2.0.

    Raises ``ValueError`` with an exact message on the first failed
    invariant, in the documented order. The returned ``StrategistInput``
    wraps the exact same ``ContentCandidate`` object — no copy, no
    reconstruction, no serialization.
    """
    # 1. Stage must already be SELECTED (SELECT owns the stage transition).
    if content_candidate.stage is not CandidateStage.SELECTED:
        raise ValueError(_ERROR_STAGE)

    # 2. A strategic selection must exist.
    if content_candidate.selection is None:
        raise ValueError(_ERROR_MISSING_SELECTION)

    # 3. Bind the selection (typing: narrowed non-None from check 2).
    selection = content_candidate.selection

    # 4. SELECT must have actually selected the candidate.
    if selection.selected is not True:
        raise ValueError(_ERROR_NOT_SELECTED)

    # 5. SELECT must have recommended a concrete format.
    if selection.recommended_format is None:
        raise ValueError(_ERROR_MISSING_FORMAT)

    # 6. SELECT must have chosen at least one target platform.
    if not selection.target_platforms:
        raise ValueError(_ERROR_MISSING_PLATFORMS)

    # 7. Classification must have produced an explicit content cluster.
    if content_candidate.candidate.content_cluster is None:
        raise ValueError(_ERROR_MISSING_CLUSTER)

    # 8. All SELECT invariants hold — bind unchanged, no copied fields.
    return StrategistInput(
        content_candidate=content_candidate,
    )
