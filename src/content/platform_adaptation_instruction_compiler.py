"""Deterministic platform adaptation instruction compiler (Stage 18D-B).

Pure snapshot boundary:

    AdaptationSourceContent + PlatformAdaptationSpec
        + output_language + metadata
        -> PlatformAdaptationInstruction

Snapshot only. Policy lookup belongs to 18B; variant construction belongs
to 18C; textual transformation belongs to a later executor. No validation.
"""

from typing import Any, Mapping

from src.domain.platform_adaptation import (
    AdaptationSourceContent,
    PlatformAdaptationInstruction,
    PlatformAdaptationSpec,
)

__all__ = [
    "compile_platform_adaptation_instruction",
]


def compile_platform_adaptation_instruction(
    source: AdaptationSourceContent,
    spec: PlatformAdaptationSpec,
    *,
    output_language: str,
    metadata: Mapping[str, Any],
) -> PlatformAdaptationInstruction:
    return PlatformAdaptationInstruction(
        candidate_id=source.candidate_id,
        source_content_id=source.content_id,
        platform=spec.platform,
        content_kind=spec.content_kind,
        source_language=source.language,
        output_language=output_language,
        requires_title=spec.requires_title,
        allows_external_link=spec.allows_external_link,
        max_characters=spec.max_characters,
        structure=spec.structure,
        tone=spec.tone,
        source_title=source.title,
        source_body=source.body,
        source_cta=source.cta,
        source_cta_link=source.cta_link,
        metadata=metadata,
    )
