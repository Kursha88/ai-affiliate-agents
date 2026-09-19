"""Deterministic research-phase lifecycle / orchestration policy (Stage 17F).

Pure diagnostic + transition boundary deciding WHICH existing Stage 16C
lifecycle transition should happen for the research phase:

    ContentPackageV2
        -> 17B deterministic planning (plan_research_requirements /
           plan_experiment on package.strategy)
        -> diagnose required gates against typed execution results
        -> PackageStage target or None
        -> transition_package_stage(...) -> new ContentPackageV2

17F never infers research necessity from StrategistPlan flags alone: 17B
remains the single source of truth, so a COMPARISON format still gates on
research even when research_required=False. An execution result is only
accepted for a planned gate when it matches the deterministic planned
requirements/plan exactly (dataclass equality). Attaching artifacts is 17E;
17F neither attaches nor inspects artifacts, and it changes state only by
delegating to the Stage 16C transition authority.
"""

from typing import Optional

from src.content.content_package_lifecycle import transition_package_stage
from src.domain.content_package import (
    ContentPackageV2,
    PackageStage,
)
from src.domain.research_execution import (
    ExperimentExecutionResult,
    ExperimentExecutionStatus,
    ResearchExecutionResult,
    ResearchExecutionStatus,
)
from src.research.research_requirement_planner import (
    plan_experiment,
    plan_research_requirements,
)

__all__ = [
    "research_phase_required",
    "determine_research_phase_target",
    "advance_research_phase",
]

_SUPPORTED_STAGES = (
    PackageStage.STRATEGY_READY,
    PackageStage.RESEARCH_PENDING,
)

_RESEARCH_MANUAL_REVIEW_STATUSES = (
    ResearchExecutionStatus.INSUFFICIENT,
    ResearchExecutionStatus.FAILED,
    ResearchExecutionStatus.MANUAL_REVIEW,
)

_EXPERIMENT_MANUAL_REVIEW_STATUSES = (
    ExperimentExecutionStatus.INCONCLUSIVE,
    ExperimentExecutionStatus.FAILED,
    ExperimentExecutionStatus.MANUAL_REVIEW,
)


def research_phase_required(
    package: ContentPackageV2,
) -> bool:
    """True when deterministic planning yields any research/experiment work."""
    requirements = plan_research_requirements(package.strategy)
    experiment_plan = plan_experiment(package.strategy)
    return bool(requirements) or experiment_plan is not None


def determine_research_phase_target(
    package: ContentPackageV2,
    *,
    research_result: Optional[ResearchExecutionResult] = None,
    experiment_result: Optional[ExperimentExecutionResult] = None,
) -> Optional[PackageStage]:
    """Diagnose the lifecycle target without mutating the package."""
    if package.stage not in _SUPPORTED_STAGES:
        raise ValueError(
            "research phase orchestration requires strategy_ready or research_pending stage"
        )

    if package.stage is PackageStage.STRATEGY_READY:
        if research_phase_required(package):
            return PackageStage.RESEARCH_PENDING
        return PackageStage.CREATION_PENDING

    planned_requirements = plan_research_requirements(package.strategy)
    planned_experiment = plan_experiment(package.strategy)
    research_needed = bool(planned_requirements)
    experiment_needed = planned_experiment is not None

    if not research_needed and not experiment_needed:
        raise ValueError(
            "research_pending package has no planned research or experiment work"
        )

    if research_result is not None and research_result.candidate_id != package.candidate_id:
        raise ValueError(
            "candidate_id mismatch between package and research result"
        )
    if experiment_result is not None and experiment_result.candidate_id != package.candidate_id:
        raise ValueError(
            "candidate_id mismatch between package and experiment result"
        )

    if research_needed and research_result is not None:
        if research_result.requirements != planned_requirements:
            raise ValueError(
                "research result requirements do not match planned requirements"
            )
    if experiment_needed and experiment_result is not None:
        if experiment_result.plan != planned_experiment:
            raise ValueError(
                "experiment result plan does not match planned experiment"
            )

    if (
        research_needed
        and research_result is not None
        and research_result.status in _RESEARCH_MANUAL_REVIEW_STATUSES
    ):
        return PackageStage.MANUAL_REVIEW
    if (
        experiment_needed
        and experiment_result is not None
        and experiment_result.status in _EXPERIMENT_MANUAL_REVIEW_STATUSES
    ):
        return PackageStage.MANUAL_REVIEW

    # After manual-review checks, a supplied result is either COMPLETED
    # (gate satisfied) or NOT_STARTED (gate still pending).
    research_satisfied = (
        research_result is not None
        and research_result.status is ResearchExecutionStatus.COMPLETED
    )
    experiment_satisfied = (
        experiment_result is not None
        and experiment_result.status is ExperimentExecutionStatus.COMPLETED
    )

    if research_needed and (
        research_result is None
        or research_result.status is ResearchExecutionStatus.NOT_STARTED
        or not research_satisfied
    ):
        return None
    if experiment_needed and (
        experiment_result is None
        or experiment_result.status is ExperimentExecutionStatus.NOT_STARTED
        or not experiment_satisfied
    ):
        return None

    return PackageStage.RESEARCH_READY


def advance_research_phase(
    package: ContentPackageV2,
    *,
    research_result: Optional[ResearchExecutionResult] = None,
    experiment_result: Optional[ExperimentExecutionResult] = None,
    updated_at: str,
) -> ContentPackageV2:
    """Advance the package through the diagnosed research-phase transition."""
    target_stage = determine_research_phase_target(
        package,
        research_result=research_result,
        experiment_result=experiment_result,
    )
    if target_stage is None:
        return package
    return transition_package_stage(
        package,
        target_stage,
        updated_at=updated_at,
    )
