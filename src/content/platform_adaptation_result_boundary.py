"""Execution-result to platform-variant boundary (Stage 18D-D2).

Deterministic post-execution plumbing:

    AdaptationSourceContent
    + PlatformAdaptationSpec
    + PlatformAdaptationExecutionResult (COMPLETED, correlated)
        -> build_platform_content_variant (18C)
        -> PlatformContentVariant

Correlation and status gating only. Variant identity, title policy, and
link policy stay owned by the 18C builder. No content transformation.
"""

from src.content.platform_variant_builder import build_platform_content_variant
from src.domain.platform_adaptation import (
    AdaptationSourceContent,
    PlatformAdaptationSpec,
    PlatformContentVariant,
)
from src.domain.platform_adaptation_execution import (
    AdaptationExecutionStatus,
    PlatformAdaptationExecutionResult,
)

__all__ = [
    "build_platform_variant_from_execution_result",
]


def build_platform_variant_from_execution_result(
    source: AdaptationSourceContent,
    spec: PlatformAdaptationSpec,
    result: PlatformAdaptationExecutionResult,
) -> PlatformContentVariant:
    if result.candidate_id != source.candidate_id:
        raise ValueError("candidate_id mismatch")
    if result.source_content_id != source.content_id:
        raise ValueError("source_content_id mismatch")
    if result.platform != spec.platform:
        raise ValueError("platform mismatch")
    if result.content_kind != spec.content_kind:
        raise ValueError("content_kind mismatch")
    if result.status is not AdaptationExecutionStatus.COMPLETED:
        raise ValueError("execution result is not completed")
    return build_platform_content_variant(
        source,
        spec,
        title=result.title,
        body=result.body,
        cta=result.cta,
        language=result.output_language,
        metadata=result.metadata,
    )
