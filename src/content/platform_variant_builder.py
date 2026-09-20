"""Deterministic platform content variant builder (Stage 18C).

Pure construction boundary:

    AdaptationSourceContent + PlatformAdaptationSpec + adapted fields
        -> PlatformContentVariant

Construction only. Policy lookup belongs to 18B; textual transformation
belongs to a later stage. No validation.
"""

from typing import Any, Mapping

from src.domain.platform_adaptation import (
    AdaptationSourceContent,
    PlatformAdaptationSpec,
    PlatformContentVariant,
)

__all__ = [
    "build_platform_content_variant",
]


def build_platform_content_variant(
    source: AdaptationSourceContent,
    spec: PlatformAdaptationSpec,
    *,
    title: str,
    body: str,
    cta: str,
    metadata: Mapping[str, Any],
) -> PlatformContentVariant:
    return PlatformContentVariant(
        variant_id=f"{source.content_id}:{spec.platform.value}",
        candidate_id=source.candidate_id,
        source_content_id=source.content_id,
        platform=spec.platform,
        content_kind=spec.content_kind,
        title=title if spec.requires_title else "",
        body=body,
        cta=cta,
        cta_link=(
            source.cta_link
            if spec.allows_external_link
            else ""
        ),
        language=source.language,
        metadata=metadata,
    )
