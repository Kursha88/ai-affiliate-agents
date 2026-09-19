"""Research and experiment execution domain contracts (Stage 17, Step 17A).

Immutable vocabulary for the execution layer that later produces structured
research and experiment outputs BEFORE they are attached to a content
package:

    research requirements -> evidence records -> ResearchExecutionResult
    experiment plans -> observations -> ExperimentExecutionResult

Step 17A is CONTRACTS ONLY: no planner, no execution logic, no network,
web search, APIs, RSS, AI, filesystem, subprocess, persistence, package
mutation, artifact creation, lifecycle transitions, serialization,
validation, or internally generated timestamps.

Requirement origins deliberately distinguish upstream SELECT flags
(``select_flag``) from requirements intrinsic to the selected content
format (``content_format``) and operator-supplied ones (``manual``): a
format such as a comparison structurally needs evidence even when the
upstream plan says research_required=False. Stage 17A never mutates or
reinterprets upstream strategy; a later 17B planner derives requirements.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Optional, Tuple

__all__ = [
    "RequirementOrigin",
    "ResearchRequirementKind",
    "EvidenceKind",
    "ResearchExecutionStatus",
    "ExperimentExecutionStatus",
    "ResearchRequirement",
    "EvidenceRecord",
    "ResearchExecutionResult",
    "ExperimentPlan",
    "ExperimentObservation",
    "ExperimentExecutionResult",
]


class RequirementOrigin(StrEnum):
    """Why a research requirement exists.

    SELECT_FLAG: upstream SELECT explicitly requested it.
    CONTENT_FORMAT: intrinsic to the selected content format.
    MANUAL: explicitly supplied by a later operator/orchestrator.
    """

    SELECT_FLAG = "select_flag"
    CONTENT_FORMAT = "content_format"
    MANUAL = "manual"


class ResearchRequirementKind(StrEnum):
    """What evidence a research requirement asks for.

    Deliberately no generic "OTHER": unknown future requirements must
    require an explicit contract update.
    """

    PRIMARY_SOURCE = "primary_source"
    SUPPORTING_EVIDENCE = "supporting_evidence"
    COMPARISON_TARGET = "comparison_target"
    COUNTERPOINT = "counterpoint"
    IMPLEMENTATION_DETAILS = "implementation_details"
    REAL_WORLD_EXAMPLE = "real_world_example"


class EvidenceKind(StrEnum):
    """Classification of one normalized evidence item."""

    PRIMARY_SOURCE = "primary_source"
    SUPPORTING_SOURCE = "supporting_source"
    COMPARISON_TARGET = "comparison_target"
    COUNTERPOINT = "counterpoint"
    DOCUMENTATION = "documentation"
    REPOSITORY = "repository"
    REAL_WORLD_EXAMPLE = "real_world_example"


class ResearchExecutionStatus(StrEnum):
    """Outcome vocabulary for a research execution run. No transition logic."""

    NOT_STARTED = "not_started"
    COMPLETED = "completed"
    INSUFFICIENT = "insufficient"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class ExperimentExecutionStatus(StrEnum):
    """Outcome vocabulary for an experiment execution run. No transition logic."""

    NOT_STARTED = "not_started"
    COMPLETED = "completed"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class ResearchRequirement:
    """One research requirement derived by a later planner.

    ``minimum_items`` has no range validation here; ``required`` records
    whether later execution may proceed without satisfying this requirement.
    """

    requirement_id: str
    kind: ResearchRequirementKind
    origin: RequirementOrigin
    query: str
    minimum_items: int
    required: bool


@dataclass(frozen=True)
class EvidenceRecord:
    """One normalized evidence item.

    ``source_url`` stays opaque here, ``summary`` is not a verbatim article
    body, and ``metadata`` carries source-specific structured context.
    """

    evidence_id: str
    kind: EvidenceKind
    title: str
    source_url: str
    source_name: str
    captured_at: str
    summary: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class ResearchExecutionResult:
    """Aggregate output of a later research executor.

    Exists independently of any package aggregate: ``candidate_id`` is the
    soft correlation key and no package artifact or persistence identity
    lives here.
    """

    candidate_id: str
    requirements: Tuple[ResearchRequirement, ...]
    evidence: Tuple[EvidenceRecord, ...]
    status: ResearchExecutionStatus
    started_at: str
    completed_at: Optional[str]
    notes: str


@dataclass(frozen=True)
class ExperimentPlan:
    """Descriptive experiment plan.

    ``procedure`` steps are descriptive only: no command strings, no
    shell/process semantics, no external side effects. 17A executes nothing.
    """

    experiment_id: str
    candidate_id: str
    hypothesis: str
    procedure: Tuple[str, ...]
    success_criteria: Tuple[str, ...]
    required: bool


@dataclass(frozen=True)
class ExperimentObservation:
    """One normalized observation emitted by a future experiment executor.

    Deliberately string-typed: no assumptions about numeric values and no
    units domain yet.
    """

    observation_id: str
    label: str
    value: str
    notes: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class ExperimentExecutionResult:
    """Aggregate output of a later experiment executor.

    ``plan`` is preserved as a nested authoritative object; hypothesis,
    procedure and success criteria are never flattened.
    """

    candidate_id: str
    plan: ExperimentPlan
    observations: Tuple[ExperimentObservation, ...]
    status: ExperimentExecutionStatus
    started_at: str
    completed_at: Optional[str]
    conclusion: str
    notes: str
