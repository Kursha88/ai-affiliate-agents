"""Immutable ContentPackageV2 enrichment and lifecycle boundary (Stage 16C).

Pure, append-only enrichment plus explicit package-stage transitions for an
ALREADY-CREATED ``ContentPackageV2``:

    attach_package_artifact      -> new package with one more artifact
    attach_platform_variant      -> new package with one more variant ref
    attach_analytics_link        -> new package with one more analytics link
    transition_package_stage     -> new package at an explicitly allowed stage

Every operation returns a NEW package built with ``dataclasses.replace``;
the original package is never mutated. ``strategy`` and ``provenance`` are
always preserved by identity, and ``quality_state`` / ``publication_state``
are preserved untouched: their transition policy belongs to later dedicated
boundaries (Quality Gate, Publisher). No research, experiments, content or
media generation, QA, publishing, analytics collection, persistence, config,
filesystem, network, clock access, ID/timestamp generation, AI, or
orchestration happens here.
"""

from dataclasses import replace

from src.domain.content_package import (
    AnalyticsLink,
    ContentPackageV2,
    PackageArtifact,
    PackageStage,
    PlatformVariantRef,
)

__all__ = [
    "attach_package_artifact",
    "attach_platform_variant",
    "attach_analytics_link",
    "transition_package_stage",
]


def attach_package_artifact(
    package: ContentPackageV2,
    artifact: PackageArtifact,
    *,
    updated_at: str,
) -> ContentPackageV2:
    """Append one artifact reference; duplicate artifact_id is rejected."""
    for existing in package.artifacts:
        if existing.artifact_id == artifact.artifact_id:
            raise ValueError("duplicate package artifact_id")
    return replace(
        package,
        artifacts=package.artifacts + (artifact,),
        updated_at=updated_at,
    )


def attach_platform_variant(
    package: ContentPackageV2,
    variant: PlatformVariantRef,
    *,
    updated_at: str,
) -> ContentPackageV2:
    """Append one platform-variant reference; duplicate variant_id is rejected.

    Two different variant IDs for the same platform are allowed here:
    platform uniqueness/version semantics belong to later platform
    adaptation logic.
    """
    for existing in package.platform_variants:
        if existing.variant_id == variant.variant_id:
            raise ValueError("duplicate platform variant_id")
    return replace(
        package,
        platform_variants=package.platform_variants + (variant,),
        updated_at=updated_at,
    )


def attach_analytics_link(
    package: ContentPackageV2,
    analytics_link: AnalyticsLink,
    *,
    updated_at: str,
) -> ContentPackageV2:
    """Append one analytics link; duplicate analytics_id is rejected."""
    for existing in package.analytics_links:
        if existing.analytics_id == analytics_link.analytics_id:
            raise ValueError("duplicate analytics_id")
    return replace(
        package,
        analytics_links=package.analytics_links + (analytics_link,),
        updated_at=updated_at,
    )


# Explicit lifecycle vocabulary. Vocabulary only: choosing WHICH path to
# take (e.g. research vs direct creation from STRATEGY_READY) belongs to
# later orchestration. MANUAL_REVIEW and ARCHIVED are terminal in 16C;
# resume-from-review policy is intentionally deferred.
_ALLOWED_STAGE_TRANSITIONS = {
    PackageStage.STRATEGY_READY: (
        PackageStage.RESEARCH_PENDING,
        PackageStage.CREATION_PENDING,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.RESEARCH_PENDING: (
        PackageStage.RESEARCH_READY,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.RESEARCH_READY: (
        PackageStage.CREATION_PENDING,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.CREATION_PENDING: (
        PackageStage.CONTENT_READY,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.CONTENT_READY: (
        PackageStage.ADAPTATION_PENDING,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.ADAPTATION_PENDING: (
        PackageStage.VARIANTS_READY,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.VARIANTS_READY: (
        PackageStage.QA_PENDING,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.QA_PENDING: (
        PackageStage.APPROVED,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.APPROVED: (
        PackageStage.PUBLISHING,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.PUBLISHING: (
        PackageStage.PUBLISHED,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.PUBLISHED: (
        PackageStage.ANALYZED,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.ANALYZED: (
        PackageStage.ARCHIVED,
        PackageStage.MANUAL_REVIEW,
    ),
    PackageStage.ARCHIVED: (),
    PackageStage.MANUAL_REVIEW: (),
}


def transition_package_stage(
    package: ContentPackageV2,
    target_stage: PackageStage,
    *,
    updated_at: str,
) -> ContentPackageV2:
    """Move the package to an explicitly allowed target stage."""
    allowed = _ALLOWED_STAGE_TRANSITIONS[package.stage]
    if target_stage not in allowed:
        raise ValueError(
            f"invalid package stage transition: {package.stage.value} -> {target_stage.value}"
        )
    return replace(
        package,
        stage=target_stage,
        updated_at=updated_at,
    )
