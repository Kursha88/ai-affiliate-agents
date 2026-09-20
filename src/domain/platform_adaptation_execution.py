"""Platform adaptation execution result contracts (Stage 18D-C).

Normalized textual adaptation output:

    PlatformAdaptationInstruction
        -> (future executor)
        -> PlatformAdaptationExecutionResult
        -> (future execution-to-variant boundary)
        -> 18C builder
        -> PlatformContentVariant

Contracts only: no executor, no normalization, no validation. Outbound
links stay owned by AdaptationSourceContent; variant identity stays owned
by the 18C builder.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from src.domain.platform_adaptation import AdaptationContentKind
from src.domain.strategy import TargetPlatform

__all__ = [
    "AdaptationExecutionStatus",
    "PlatformAdaptationExecutionResult",
]


class AdaptationExecutionStatus(StrEnum):
    """Execution outcome vocabulary for platform adaptation."""

    COMPLETED = "completed"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class PlatformAdaptationExecutionResult:
    """Normalized textual adaptation output for exactly one platform."""

    candidate_id: str
    source_content_id: str
    platform: TargetPlatform
    content_kind: AdaptationContentKind
    title: str
    body: str
    cta: str
    output_language: str
    status: AdaptationExecutionStatus
    metadata: Mapping[str, Any]
