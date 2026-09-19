"""Deterministic research requirement / experiment planner (Stage 17B).

Pure planning boundary converting already-final strategy decisions into
execution requirements:

    StrategistPlan -> plan_research_requirements() -> Tuple[ResearchRequirement, ...]
    StrategistPlan -> plan_experiment()             -> Optional[ExperimentPlan]

The planner consumes ``content_format``, ``research_required`` and
``experiment_required`` exactly as supplied and never mutates or reinterprets
the StrategistPlan. It ADDS requirements intrinsic to the selected content
format: e.g. a COMPARISON format structurally needs a comparison target even
when upstream SELECT said research_required=False (the production gap
observed during live validation). Choosing between alternative paths belongs
to later orchestration; 17B plans only and executes nothing.
"""

from typing import Optional, Tuple

from src.domain.research_execution import (
    ExperimentPlan,
    RequirementOrigin,
    ResearchRequirement,
    ResearchRequirementKind,
)
from src.domain.strategy import ContentFormat
from src.domain.strategist import StrategistPlan

__all__ = [
    "plan_research_requirements",
    "plan_experiment",
]

# Intrinsic per-format research policy: (kind, query, minimum_items) or None
# when the format carries no intrinsic research requirement. Direct indexing
# only: an unknown future ContentFormat member must fail loudly until the
# policy is explicitly updated.
_FORMAT_RESEARCH_POLICY = {
    ContentFormat.BREAKING_NEWS: (
        ResearchRequirementKind.PRIMARY_SOURCE,
        "Confirm the story against the authoritative primary source",
        1,
    ),
    ContentFormat.TOOL_DISCOVERY: (
        ResearchRequirementKind.PRIMARY_SOURCE,
        "Find authoritative product documentation or repository for the selected tool",
        1,
    ),
    ContentFormat.PRACTICAL_GUIDE: (
        ResearchRequirementKind.IMPLEMENTATION_DETAILS,
        "Find concrete implementation details needed to reproduce the guide",
        1,
    ),
    ContentFormat.COMPARISON: (
        ResearchRequirementKind.COMPARISON_TARGET,
        "Find one credible alternative to compare with the selected topic",
        1,
    ),
    ContentFormat.EXPERIMENT: None,
    ContentFormat.WORKFLOW: (
        ResearchRequirementKind.IMPLEMENTATION_DETAILS,
        "Find concrete implementation details needed to reproduce the workflow",
        1,
    ),
    ContentFormat.PROMPT: None,
    ContentFormat.CASE_STUDY: (
        ResearchRequirementKind.REAL_WORLD_EXAMPLE,
        "Find one concrete real-world example relevant to the selected topic",
        1,
    ),
    ContentFormat.OPINION_ANALYSIS: (
        ResearchRequirementKind.COUNTERPOINT,
        "Find one credible counterpoint or materially different perspective",
        1,
    ),
    ContentFormat.ROUNDUP: (
        ResearchRequirementKind.SUPPORTING_EVIDENCE,
        "Find at least three credible items suitable for the roundup",
        3,
    ),
}


def plan_research_requirements(
    strategist_plan: StrategistPlan,
) -> Tuple[ResearchRequirement, ...]:
    """Plan research requirements for a finalized StrategistPlan.

    Order is deterministic: format-intrinsic requirements first, then the
    single SELECT_FLAG requirement when ``research_required`` is True. Same
    kinds from different origins are never deduplicated: the origin captures
    a distinct reason for the requirement.
    """
    requirements = []
    policy = _FORMAT_RESEARCH_POLICY[strategist_plan.content_format]
    if policy is not None:
        kind, query, minimum_items = policy
        requirements.append(
            ResearchRequirement(
                requirement_id=(
                    f"{strategist_plan.candidate_id}:format:{kind.value}"
                ),
                kind=kind,
                origin=RequirementOrigin.CONTENT_FORMAT,
                query=query,
                minimum_items=minimum_items,
                required=True,
            )
        )
    if strategist_plan.research_required:
        requirements.append(
            ResearchRequirement(
                requirement_id=(
                    f"{strategist_plan.candidate_id}:select:supporting_evidence"
                ),
                kind=ResearchRequirementKind.SUPPORTING_EVIDENCE,
                origin=RequirementOrigin.SELECT_FLAG,
                query="Gather additional credible evidence for the selected topic",
                minimum_items=1,
                required=True,
            )
        )
    return tuple(requirements)


def plan_experiment(
    strategist_plan: StrategistPlan,
) -> Optional[ExperimentPlan]:
    """Plan an experiment when required by flag or by the EXPERIMENT format.

    Mirrors the research policy: SELECT may explicitly require an experiment,
    and the EXPERIMENT format intrinsically requires one.
    """
    if (
        not strategist_plan.experiment_required
        and strategist_plan.content_format is not ContentFormat.EXPERIMENT
    ):
        return None
    return ExperimentPlan(
        experiment_id=f"{strategist_plan.candidate_id}:experiment",
        candidate_id=strategist_plan.candidate_id,
        hypothesis=(
            f"Testing {strategist_plan.topic} produces an observable practical result"
        ),
        procedure=(
            "Define the expected result and baseline",
            "Run the described approach in a controlled test",
            "Record the observable outcome",
            "Compare the outcome with the expected result",
        ),
        success_criteria=(
            "The procedure can be completed as described",
            "The outcome is observable and can support a practical conclusion",
        ),
        required=True,
    )
