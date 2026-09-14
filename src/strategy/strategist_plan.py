"""Deterministic StrategistPlan assembler (Stage 15, Step 15C).

PURE ASSEMBLER: ``StrategistInput`` + explicit strategist-owned
enrichment → ``StrategistPlan``. Every SELECT-owned decision
(candidate_id, content_cluster, content_format, target_platforms,
research_required, experiment_required) is preserved exactly from the
authoritative ``ContentCandidate`` inside the input; nothing is chosen,
recomputed, normalized or defaulted here.

This layer is downstream of the validated boundary layer: the input is
expected to have passed ``CandidateStage.SELECTED`` / selection
completeness checks there. Only three narrow defensive fail-closed
guards are added for the Optional values this assembler actually needs
(selection presence, recommended format, content cluster) — stage,
``selection.selected`` and platform emptiness are NOT revalidated:
they remain boundary responsibilities.

The strategist-owned enrichment (angle, hook, objective, cta, cta_link,
tone, structure, language, mode) comes exactly from the explicit
keyword-only arguments — no generation, no rules, no AI, no defaults.
"""

from src.domain.strategist import StrategistInput, StrategistPlan

__all__ = ["build_strategist_plan"]

_ERROR_MISSING_SELECTION = "strategist input missing strategic selection"
_ERROR_MISSING_FORMAT = "strategist input missing recommended format"
_ERROR_MISSING_CLUSTER = "strategist input missing content cluster"


def build_strategist_plan(
    strategist_input: StrategistInput,
    *,
    angle: str,
    hook: str,
    objective: str,
    cta: str,
    cta_link: str,
    tone: str,
    structure: tuple[str, ...],
    language: str,
    mode: str,
) -> StrategistPlan:
    """Assemble a StrategistPlan with lossless SELECT preservation.

    Defensive guards (in this exact order) protect against malformed
    manually-created ``StrategistInput``:

    1. ``candidate.selection`` must not be None
    2. (bind) ``selection = candidate.selection``
    3. ``selection.recommended_format`` must not be None
    4. ``candidate.candidate.content_cluster`` must not be None

    The plan's SELECT-owned fields are forwarded by identity — the
    ``target_platforms`` tuple is passed through untouched.
    """
    candidate = strategist_input.content_candidate

    # 1. A strategic selection must exist.
    if candidate.selection is None:
        raise ValueError(_ERROR_MISSING_SELECTION)

    # 2. Bind the selection (narrowed non-None by guard 1).
    selection = candidate.selection

    # 3. The recommended format must be present.
    if selection.recommended_format is None:
        raise ValueError(_ERROR_MISSING_FORMAT)

    # 4. The content cluster must be present.
    if candidate.candidate.content_cluster is None:
        raise ValueError(_ERROR_MISSING_CLUSTER)

    return StrategistPlan(
        candidate_id=candidate.candidate.candidate_id,
        topic=candidate.candidate.title,
        content_cluster=candidate.candidate.content_cluster,
        content_format=selection.recommended_format,
        target_platforms=selection.target_platforms,
        research_required=selection.research_required,
        experiment_required=selection.experiment_required,
        angle=angle,
        hook=hook,
        objective=objective,
        cta=cta,
        cta_link=cta_link,
        tone=tone,
        structure=structure,
        language=language,
        mode=mode,
    )
