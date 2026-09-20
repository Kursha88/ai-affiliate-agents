"""Content package platform-variant attachment boundary (Stage 18E-B).

Adaptation-specific gate before immutable attachment:

    ContentPackageV2 + PlatformContentVariant + PlatformVariantRef
        -> correlation / stage / initial-state / uniqueness checks
        -> attach_platform_variant (Stage 16C)
        -> new ContentPackageV2

One final textual variant per target platform. Stage advancement to
VARIANTS_READY belongs to later completeness orchestration (18E-C).
"""

from src.content.content_package_lifecycle import attach_platform_variant
from src.domain.content_package import (
    ContentPackageV2,
    PackageStage,
    PlatformVariantRef,
    PublicationState,
    QualityState,
)
from src.domain.platform_adaptation import PlatformContentVariant

__all__ = [
    "attach_adapted_platform_variant",
]


def attach_adapted_platform_variant(
    package: ContentPackageV2,
    variant: PlatformContentVariant,
    variant_ref: PlatformVariantRef,
    *,
    updated_at: str,
) -> ContentPackageV2:
    if package.stage is not PackageStage.ADAPTATION_PENDING:
        raise ValueError("package is not adaptation pending")
    if package.candidate_id != variant.candidate_id:
        raise ValueError("candidate_id mismatch")
    if variant.platform not in package.strategy.target_platforms:
        raise ValueError("platform is not targeted by package strategy")
    if variant_ref.variant_id != variant.variant_id:
        raise ValueError("variant_id mismatch")
    if variant_ref.platform != variant.platform:
        raise ValueError("platform mismatch")
    if variant_ref.quality_state is not QualityState.NOT_CHECKED:
        raise ValueError("variant ref quality state is not initial")
    if variant_ref.publication_state is not PublicationState.NOT_READY:
        raise ValueError("variant ref publication state is not initial")
    for existing in package.platform_variants:
        if existing.platform == variant.platform:
            raise ValueError("duplicate platform variant")
    return attach_platform_variant(
        package,
        variant_ref,
        updated_at=updated_at,
    )
