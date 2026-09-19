"""ContentPackageV2 integration for research/experiment results (Stage 17E).

Thin integration boundary projecting finalized execution results into
package artifacts and attaching them through the existing Stage 16C
lifecycle:

    ResearchExecutionResult  -> PackageArtifact(kind=RESEARCH)  -> attach
    ExperimentExecutionResult -> PackageArtifact(kind=EXPERIMENT) -> attach

17E does NOT execute research or experiments, does NOT advance the package
stage (lifecycle advancement is a separate orchestration decision), and
does NOT persist anything. Artifact identity is deterministic
(``{candidate_id}:research`` / ``{candidate_id}:experiment``); metadata is
an explicitly listed scalar projection only, never a serialization of the
underlying requirements, evidence, or observations. The only validation is
candidate consistency between the package and the result at the attach
boundary.
"""

from src.content.content_package_lifecycle import attach_package_artifact
from src.domain.content_package import (
    ArtifactKind,
    ContentPackageV2,
    PackageArtifact,
)
from src.domain.research_execution import (
    ExperimentExecutionResult,
    ResearchExecutionResult,
)

__all__ = [
    "build_research_package_artifact",
    "build_experiment_package_artifact",
    "attach_research_result",
    "attach_experiment_result",
]


def build_research_package_artifact(
    result: ResearchExecutionResult,
    *,
    uri: str,
) -> PackageArtifact:
    """Project a research execution result into one package artifact."""
    return PackageArtifact(
        artifact_id=f"{result.candidate_id}:research",
        kind=ArtifactKind.RESEARCH,
        uri=uri,
        title="Research execution result",
        metadata={
            "candidate_id": result.candidate_id,
            "status": result.status.value,
            "requirement_count": len(result.requirements),
            "evidence_count": len(result.evidence),
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "notes": result.notes,
        },
    )


def build_experiment_package_artifact(
    result: ExperimentExecutionResult,
    *,
    uri: str,
) -> PackageArtifact:
    """Project an experiment execution result into one package artifact."""
    return PackageArtifact(
        artifact_id=f"{result.candidate_id}:experiment",
        kind=ArtifactKind.EXPERIMENT,
        uri=uri,
        title="Experiment execution result",
        metadata={
            "candidate_id": result.candidate_id,
            "experiment_id": result.plan.experiment_id,
            "status": result.status.value,
            "observation_count": len(result.observations),
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "conclusion": result.conclusion,
            "notes": result.notes,
        },
    )


def attach_research_result(
    package: ContentPackageV2,
    result: ResearchExecutionResult,
    *,
    uri: str,
    updated_at: str,
) -> ContentPackageV2:
    """Attach a research execution result artifact to the package."""
    if package.candidate_id != result.candidate_id:
        raise ValueError(
            "candidate_id mismatch between package and research result"
        )
    artifact = build_research_package_artifact(
        result,
        uri=uri,
    )
    return attach_package_artifact(
        package,
        artifact,
        updated_at=updated_at,
    )


def attach_experiment_result(
    package: ContentPackageV2,
    result: ExperimentExecutionResult,
    *,
    uri: str,
    updated_at: str,
) -> ContentPackageV2:
    """Attach an experiment execution result artifact to the package."""
    if package.candidate_id != result.candidate_id:
        raise ValueError(
            "candidate_id mismatch between package and experiment result"
        )
    artifact = build_experiment_package_artifact(
        result,
        uri=uri,
    )
    return attach_package_artifact(
        package,
        artifact,
        updated_at=updated_at,
    )
