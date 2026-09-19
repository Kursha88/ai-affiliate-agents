"""Deterministic ContentPackageV2 builder boundary (Stage 16, Step 16B).

Pure construction of the initial Content Package 2.0 aggregate from
already-final upstream objects:

    ContentCandidate + StrategistPlan + caller-supplied identity/time
    -> ContentPackageV2

The builder performs NO research, experiments, content or variant
generation, artifact generation, publishing, persistence, config,
filesystem, network, clock, UUID/hash generation, or AI calls, and it
never mutates or recomputes its inputs. It performs only the minimum
structural consistency checks that prevent upstream data loss; all
broader domain validation belongs to later boundaries.
"""

from typing import Optional

from src.domain.content_package import (
    ContentPackageV2,
    PackageStage,
    PublicationState,
    QualityState,
    SourceProvenance,
)
from src.domain.strategy import CandidateStage, ContentCandidate
from src.domain.strategist import StrategistPlan

__all__ = ["build_content_package"]


def build_content_package(
    content_candidate: ContentCandidate,
    strategist_plan: StrategistPlan,
    *,
    package_id: str,
    created_at: str,
    updated_at: str,
    legacy_content_id: Optional[str] = None,
) -> ContentPackageV2:
    """Build the initial ContentPackageV2 for a selected candidate.

    Package identity and timestamps are caller-supplied values used
    exactly as given: nothing is generated, defaulted, or normalized.
    The upstream ``StrategistPlan`` is preserved by reference.
    """
    if content_candidate.stage != CandidateStage.SELECTED:
        raise ValueError("content candidate is not at selected stage")
    if content_candidate.selection is None:
        raise ValueError("content candidate missing strategic selection")
    if content_candidate.selection.selected is not True:
        raise ValueError("strategic selection is not selected")
    if content_candidate.candidate.candidate_id != strategist_plan.candidate_id:
        raise ValueError("candidate_id mismatch between candidate and strategist plan")
    if content_candidate.candidate.content_cluster != strategist_plan.content_cluster:
        raise ValueError("content_cluster mismatch between candidate and strategist plan")
    if content_candidate.selection.recommended_format != strategist_plan.content_format:
        raise ValueError("content_format mismatch between selection and strategist plan")
    if content_candidate.selection.target_platforms != strategist_plan.target_platforms:
        raise ValueError("target_platforms mismatch between selection and strategist plan")
    if content_candidate.selection.research_required != strategist_plan.research_required:
        raise ValueError("research_required mismatch between selection and strategist plan")
    if content_candidate.selection.experiment_required != strategist_plan.experiment_required:
        raise ValueError("experiment_required mismatch between selection and strategist plan")

    provenance = SourceProvenance(
        candidate_id=content_candidate.candidate.candidate_id,
        source_url=content_candidate.candidate.source_url,
        source_name=content_candidate.candidate.source_name,
        source_type=content_candidate.candidate.source_type.value,
        discovered_at=content_candidate.candidate.discovered_at,
        published_at=content_candidate.candidate.published_at,
        verification_status=content_candidate.verification.verification_status.value,
        verification_confidence=content_candidate.verification.confidence,
    )
    return ContentPackageV2(
        package_id=package_id,
        candidate_id=content_candidate.candidate.candidate_id,
        strategy=strategist_plan,
        provenance=provenance,
        stage=PackageStage.STRATEGY_READY,
        quality_state=QualityState.NOT_CHECKED,
        publication_state=PublicationState.NOT_READY,
        artifacts=(),
        platform_variants=(),
        analytics_links=(),
        created_at=created_at,
        updated_at=updated_at,
        legacy_content_id=legacy_content_id,
    )
