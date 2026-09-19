"""Deterministic offline research evidence evaluator (Stage 17C).

Pure evaluation boundary over ALREADY-NORMALIZED evidence and
ALREADY-PLANNED requirements:

    requirements + evidence + caller-supplied candidate/time values
    -> evaluate_research_execution(...) -> ResearchExecutionResult

17C does NOT discover or fetch evidence and generates no requirements,
IDs, or timestamps. It decides only which evidence kinds can satisfy which
requirement kinds, whether every REQUIRED requirement has enough DISTINCT
evidence (by evidence_id only), the resulting ResearchExecutionStatus
(COMPLETED or INSUFFICIENT), and deterministic notes listing unmet required
requirement IDs in original order. Requirement origin does NOT affect
matching; the same evidence may satisfy multiple requirements (no
consumption or exclusive ownership); duplicate evidence IDs count once per
requirement but the returned evidence tuple is preserved verbatim.
"""

from typing import Optional, Tuple

from src.domain.research_execution import (
    EvidenceKind,
    EvidenceRecord,
    ResearchExecutionResult,
    ResearchExecutionStatus,
    ResearchRequirement,
    ResearchRequirementKind,
)

__all__ = [
    "evaluate_research_execution",
]

# Which EvidenceKind values can satisfy which ResearchRequirementKind.
# Direct indexing only: an unknown future requirement kind must fail loudly
# until this policy is explicitly updated.
_REQUIREMENT_EVIDENCE_POLICY = {
    ResearchRequirementKind.PRIMARY_SOURCE: (
        EvidenceKind.PRIMARY_SOURCE,
        EvidenceKind.DOCUMENTATION,
        EvidenceKind.REPOSITORY,
    ),
    ResearchRequirementKind.SUPPORTING_EVIDENCE: (
        EvidenceKind.PRIMARY_SOURCE,
        EvidenceKind.SUPPORTING_SOURCE,
        EvidenceKind.COMPARISON_TARGET,
        EvidenceKind.COUNTERPOINT,
        EvidenceKind.DOCUMENTATION,
        EvidenceKind.REPOSITORY,
        EvidenceKind.REAL_WORLD_EXAMPLE,
    ),
    ResearchRequirementKind.COMPARISON_TARGET: (
        EvidenceKind.COMPARISON_TARGET,
    ),
    ResearchRequirementKind.COUNTERPOINT: (
        EvidenceKind.COUNTERPOINT,
    ),
    ResearchRequirementKind.IMPLEMENTATION_DETAILS: (
        EvidenceKind.DOCUMENTATION,
        EvidenceKind.REPOSITORY,
    ),
    ResearchRequirementKind.REAL_WORLD_EXAMPLE: (
        EvidenceKind.REAL_WORLD_EXAMPLE,
    ),
}


def evaluate_research_execution(
    *,
    candidate_id: str,
    requirements: Tuple[ResearchRequirement, ...],
    evidence: Tuple[EvidenceRecord, ...],
    started_at: str,
    completed_at: Optional[str],
) -> ResearchExecutionResult:
    """Evaluate evidence against requirements; never mutates its inputs."""
    unsatisfied_ids = []
    for requirement in requirements:
        compatible_kinds = _REQUIREMENT_EVIDENCE_POLICY[requirement.kind]
        matching_ids = {
            record.evidence_id
            for record in evidence
            if record.kind in compatible_kinds
        }
        satisfied = len(matching_ids) >= requirement.minimum_items
        if requirement.required and not satisfied:
            unsatisfied_ids.append(requirement.requirement_id)

    if unsatisfied_ids:
        status = ResearchExecutionStatus.INSUFFICIENT
        notes = (
            "Unsatisfied required requirements: "
            + ", ".join(unsatisfied_ids)
        )
    else:
        status = ResearchExecutionStatus.COMPLETED
        notes = ""

    return ResearchExecutionResult(
        candidate_id=candidate_id,
        requirements=requirements,
        evidence=evidence,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        notes=notes,
    )
