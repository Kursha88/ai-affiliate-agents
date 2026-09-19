"""Content Package 2.0 domain contracts (Stage 16, Step 16A).

Central immutable aggregate for ONE selected story/topic after Strategist 2.0.
Future stages enrich it in place across the lifecycle:

    SELECT -> StrategistPlan -> ContentPackageV2 -> Research/Experiment
    artifacts -> Creation -> Platform adaptation -> Media -> Quality Gate ->
    Publication -> Analytics -> Learning

Step 16A is CONTRACTS ONLY: vocabulary enums and frozen dataclasses.
No builders, no orchestration, no persistence, no serialization, no
validation, no state-machine logic, no media domain, no I/O of any kind.
The legacy Stage 3.1 ``src.domain.strategy.ContentPackage`` remains
untouched; the temporary "V2" suffix prevents ambiguous imports during
migration.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Optional, Tuple

from src.domain.strategy import TargetPlatform
from src.domain.strategist import StrategistPlan

__all__ = [
    "PackageStage",
    "ArtifactKind",
    "QualityState",
    "PublicationState",
    "SourceProvenance",
    "PackageArtifact",
    "PlatformVariantRef",
    "AnalyticsLink",
    "ContentPackageV2",
]


class PackageStage(StrEnum):
    """Package lifecycle vocabulary. No transition logic in 16A."""

    STRATEGY_READY = "strategy_ready"
    RESEARCH_PENDING = "research_pending"
    RESEARCH_READY = "research_ready"
    CREATION_PENDING = "creation_pending"
    CONTENT_READY = "content_ready"
    ADAPTATION_PENDING = "adaptation_pending"
    VARIANTS_READY = "variants_ready"
    QA_PENDING = "qa_pending"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    ANALYZED = "analyzed"
    ARCHIVED = "archived"
    MANUAL_REVIEW = "manual_review"


class ArtifactKind(StrEnum):
    """Generic package-level artifact classification (no media domain yet)."""

    RESEARCH = "research"
    EXPERIMENT = "experiment"
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    SOURCE = "source"


class QualityState(StrEnum):
    """Aggregate QA state vocabulary. No quality logic."""

    NOT_CHECKED = "not_checked"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MANUAL_REVIEW = "manual_review"


class PublicationState(StrEnum):
    """Aggregate publication state vocabulary. No publishing logic."""

    NOT_READY = "not_ready"
    READY = "ready"
    PUBLISHING = "publishing"
    PARTIALLY_PUBLISHED = "partially_published"
    PUBLISHED = "published"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class SourceProvenance:
    """Stable provenance snapshot attached to the package.

    Plain strings for ``source_type`` / ``verification_status``: the package
    captures provenance data without owning Researcher's enum semantics.
    """

    candidate_id: str
    source_url: str
    source_name: str
    source_type: str
    discovered_at: str
    published_at: Optional[str]
    verification_status: str
    verification_confidence: float


@dataclass(frozen=True)
class PackageArtifact:
    """Generic reference to an artifact produced by later stages.

    ``uri`` is opaque here: it may be a file path, object-storage URI, URL,
    etc. Stage 16A does not interpret it.
    """

    artifact_id: str
    kind: ArtifactKind
    uri: str
    title: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class PlatformVariantRef:
    """Lightweight package-level reference to a platform-native variant.

    Deliberately NOT the legacy ``src.domain.strategy.PlatformVariant``
    publication slot; this ref belongs to Content Package 2.0.
    """

    variant_id: str
    platform: TargetPlatform
    content_ref: str
    quality_state: QualityState
    publication_state: PublicationState


@dataclass(frozen=True)
class AnalyticsLink:
    """Soft link from the package to future analytics records. No metrics."""

    analytics_id: str
    platform: Optional[TargetPlatform]
    external_post_id: Optional[str]


@dataclass(frozen=True)
class ContentPackageV2:
    """Central immutable aggregate for one selected story/topic.

    Preserves the upstream ``StrategistPlan`` as a nested authoritative
    strategy object without flattening or recomputing it. All timestamps are
    caller-supplied strings (no clock access, no parsing). ``legacy_content_id``
    is a migration aid only: no DB coupling, no foreign key.
    """

    package_id: str
    candidate_id: str
    strategy: StrategistPlan
    provenance: SourceProvenance
    stage: PackageStage
    quality_state: QualityState
    publication_state: PublicationState
    artifacts: Tuple[PackageArtifact, ...]
    platform_variants: Tuple[PlatformVariantRef, ...]
    analytics_links: Tuple[AnalyticsLink, ...]
    created_at: str
    updated_at: str
    legacy_content_id: Optional[str]
