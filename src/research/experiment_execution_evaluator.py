"""Deterministic offline experiment execution evaluator (Stage 17D).

Pure offline boundary over an ALREADY-PLANNED experiment:

    ExperimentPlan + observations + caller-supplied values
    -> evaluate_experiment_execution(...) -> ExperimentExecutionResult

No experiment is executed here. 17D evaluates EXECUTION COMPLETENESS only:
observations present -> COMPLETED, no observations -> INCONCLUSIVE.
COMPLETED means the planned experiment produced at least one normalized
observation; it is not a judgment about the hypothesis or the plan's
success criteria, which this evaluator never interprets. Semantic claim
evaluation belongs to a later quality/evaluation layer.
"""

from typing import Optional, Tuple

from src.domain.research_execution import (
    ExperimentExecutionResult,
    ExperimentExecutionStatus,
    ExperimentObservation,
    ExperimentPlan,
)

__all__ = [
    "evaluate_experiment_execution",
]


def evaluate_experiment_execution(
    *,
    plan: ExperimentPlan,
    observations: Tuple[ExperimentObservation, ...],
    started_at: str,
    completed_at: Optional[str],
    conclusion: str,
    notes: str,
) -> ExperimentExecutionResult:
    """Build the execution result from caller-supplied values, verbatim."""
    if observations:
        status = ExperimentExecutionStatus.COMPLETED
    else:
        status = ExperimentExecutionStatus.INCONCLUSIVE

    return ExperimentExecutionResult(
        candidate_id=plan.candidate_id,
        plan=plan,
        observations=observations,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        conclusion=conclusion,
        notes=notes,
    )
