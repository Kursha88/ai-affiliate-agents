"""Platform variant package-reference builder (Stage 18E-A).

Deterministic projection:

    PlatformContentVariant + caller-supplied content_ref
        -> PlatformVariantRef

Projection only: no package access, no attachment, no lifecycle
transition, no storage. content_ref is an opaque caller-owned locator;
the ref starts at NOT_CHECKED / NOT_READY.
"""

from src.domain.content_package import (
    PlatformVariantRef,
    PublicationState,
    QualityState,
)
from src.domain.platform_adaptation import PlatformContentVariant

__all__ = [
    "build_platform_variant_ref",
]


def build_platform_variant_ref(
    variant: PlatformContentVariant,
    *,
    content_ref: str,
) -> PlatformVariantRef:
    return PlatformVariantRef(
        variant_id=variant.variant_id,
        platform=variant.platform,
        content_ref=content_ref,
        quality_state=QualityState.NOT_CHECKED,
        publication_state=PublicationState.NOT_READY,
    )
