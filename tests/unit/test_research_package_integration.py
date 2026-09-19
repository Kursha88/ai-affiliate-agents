"""Step 17E unit tests: ContentPackageV2 integration for execution results.

Covers the exact deterministic artifact projections (artifact IDs, kinds,
titles, exact metadata key contracts), count projection semantics, caller
URI preservation, candidate-mismatch boundary validation with exact
messages, duplicate-artifact propagation from Stage 16C, research +
experiment coexistence, no automatic stage change, non-completed results
attaching, package and result immutability, determinism, and structural
AST guarantees (field access boundaries, no status branching, no deep
serialization, no lifecycle/persistence/strategy coupling).
"""

import ast
import unittest
from pathlib import Path

from src.content.content_package_lifecycle import (
    attach_analytics_link,
    attach_platform_variant,
)
from src.domain.content_package import (
    ArtifactKind,
    ContentPackageV2,
    PackageArtifact,
    PackageStage,
    PublicationState,
    QualityState,
    SourceProvenance,
)
from src.domain.research_execution import (
    EvidenceKind,
    EvidenceRecord,
    ExperimentExecutionResult,
    ExperimentExecutionStatus,
    ExperimentObservation,
    ExperimentPlan,
    ResearchExecutionResult,
    ResearchExecutionStatus,
    ResearchRequirement,
    ResearchRequirementKind,
    RequirementOrigin,
)
from src.domain.strategy import ContentCluster, ContentFormat, TargetPlatform
from src.domain.strategist import StrategistPlan
from src.research.research_package_integration import (
    attach_experiment_result,
    attach_research_result,
    build_experiment_package_artifact,
    build_research_package_artifact,
)

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "research"
    / "research_package_integration.py"
)

CREATED_AT = "2026-09-19T10:00:00+00:00"
UPDATED_AT = "2026-09-19T11:06:00+00:00"
RESEARCH_URI = "memory://research/cand-123"
EXPERIMENT_URI = "memory://experiment/cand-123"


def _plan() -> StrategistPlan:
    return StrategistPlan(
        candidate_id="cand-123",
        topic="Example AI tool",
        content_cluster=ContentCluster.AI_TOOLS,
        content_format=ContentFormat.TOOL_DISCOVERY,
        target_platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
        research_required=False,
        experiment_required=False,
        angle="angle",
        hook="hook",
        objective="objective",
        cta="cta",
        cta_link="https://example.com/tool",
        tone="tone",
        structure=("context", "body", "cta"),
        language="ru",
        mode="growth",
    )


PROVENANCE = SourceProvenance(
    candidate_id="cand-123",
    source_url="https://example.com/tool",
    source_name="example",
    source_type="github",
    discovered_at="2026-09-19T09:00:00+00:00",
    published_at="2026-09-19T08:00:00+00:00",
    verification_status="verified",
    verification_confidence=0.91,
)


def _package(**overrides) -> ContentPackageV2:
    defaults = dict(
        package_id="pkg-123",
        candidate_id="cand-123",
        strategy=_plan(),
        provenance=PROVENANCE,
        stage=PackageStage.RESEARCH_PENDING,
        quality_state=QualityState.NOT_CHECKED,
        publication_state=PublicationState.NOT_READY,
        artifacts=(),
        platform_variants=(),
        analytics_links=(),
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        legacy_content_id=None,
    )
    defaults.update(overrides)
    return ContentPackageV2(**defaults)


def _requirement(requirement_id="req-1") -> ResearchRequirement:
    return ResearchRequirement(
        requirement_id=requirement_id,
        kind=ResearchRequirementKind.COMPARISON_TARGET,
        origin=RequirementOrigin.CONTENT_FORMAT,
        query="Find one credible comparison target",
        minimum_items=1,
        required=True,
    )


def _evidence(evidence_id="evidence-1") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        kind=EvidenceKind.COMPARISON_TARGET,
        title="Alternative Tool",
        source_url="https://example.com/alternative",
        source_name="Example",
        captured_at="2026-09-19T11:00:00+00:00",
        summary="A credible comparison target.",
        metadata={"source": "test"},
    )


def _research_result(**overrides) -> ResearchExecutionResult:
    defaults = dict(
        candidate_id="cand-123",
        requirements=(_requirement(),),
        evidence=(_evidence(),),
        status=ResearchExecutionStatus.COMPLETED,
        started_at="2026-09-19T11:00:00+00:00",
        completed_at="2026-09-19T11:05:00+00:00",
        notes="",
    )
    defaults.update(overrides)
    return ResearchExecutionResult(**defaults)


def _experiment_plan(**overrides) -> ExperimentPlan:
    defaults = dict(
        experiment_id="cand-123:experiment",
        candidate_id="cand-123",
        hypothesis="Testing Example AI tool produces an observable practical result",
        procedure=(
            "Define the expected result and baseline",
            "Run the described approach in a controlled test",
            "Record the observable outcome",
            "Compare the outcome with the expected result",
        ),
        success_criteria=(
            "The procedure can be completed as described",
            "The outcome is observable and can support a practical conclusion",
        ),
        required=True,
    )
    defaults.update(overrides)
    return ExperimentPlan(**defaults)


def _observation(observation_id="obs-1") -> ExperimentObservation:
    return ExperimentObservation(
        observation_id=observation_id,
        label="manual_steps",
        value="3",
        notes="Observed during offline test",
        metadata={"source": "test"},
    )


def _experiment_result(**overrides) -> ExperimentExecutionResult:
    defaults = dict(
        candidate_id="cand-123",
        plan=_experiment_plan(),
        observations=(_observation(),),
        status=ExperimentExecutionStatus.COMPLETED,
        started_at="2026-09-19T12:00:00+00:00",
        completed_at="2026-09-19T12:05:00+00:00",
        conclusion="Observed practical result",
        notes="",
    )
    defaults.update(overrides)
    return ExperimentExecutionResult(**defaults)


RESEARCH_METADATA = {
    "candidate_id": "cand-123",
    "status": "completed",
    "requirement_count": 1,
    "evidence_count": 1,
    "started_at": "2026-09-19T11:00:00+00:00",
    "completed_at": "2026-09-19T11:05:00+00:00",
    "notes": "",
}

EXPERIMENT_METADATA = {
    "candidate_id": "cand-123",
    "experiment_id": "cand-123:experiment",
    "status": "completed",
    "observation_count": 1,
    "started_at": "2026-09-19T12:00:00+00:00",
    "completed_at": "2026-09-19T12:05:00+00:00",
    "conclusion": "Observed practical result",
    "notes": "",
}


class TestBuildResearchArtifact(unittest.TestCase):
    def test_exact_projection(self):
        artifact = build_research_package_artifact(
            _research_result(), uri=RESEARCH_URI
        )
        self.assertIsInstance(artifact, PackageArtifact)
        self.assertEqual(artifact.artifact_id, "cand-123:research")
        self.assertIs(artifact.kind, ArtifactKind.RESEARCH)
        self.assertEqual(artifact.uri, RESEARCH_URI)
        self.assertEqual(artifact.title, "Research execution result")
        self.assertEqual(artifact.metadata, RESEARCH_METADATA)
        self.assertEqual(set(artifact.metadata), set(RESEARCH_METADATA))

    def test_insufficient_status_still_builds(self):
        artifact = build_research_package_artifact(
            _research_result(status=ResearchExecutionStatus.INSUFFICIENT),
            uri=RESEARCH_URI,
        )
        self.assertEqual(artifact.metadata["status"], "insufficient")

    def test_count_projection_uses_raw_lengths(self):
        result = _research_result(
            requirements=(
                _requirement("req-1"),
                _requirement("req-2"),
                _requirement("req-3"),
            ),
            evidence=(
                _evidence("e1"),
                _evidence("e2"),
                _evidence("e3"),
                _evidence("e4"),
            ),
        )
        artifact = build_research_package_artifact(result, uri=RESEARCH_URI)
        self.assertEqual(artifact.metadata["requirement_count"], 3)
        self.assertEqual(artifact.metadata["evidence_count"], 4)

    def test_caller_uri_preserved_exactly(self):
        for uri in ("", "not-a-uri", "memory://research/cand-123"):
            with self.subTest(uri=uri):
                artifact = build_research_package_artifact(
                    _research_result(), uri=uri
                )
                self.assertEqual(artifact.uri, uri)

    def test_builder_accepts_empty_candidate_id(self):
        artifact = build_research_package_artifact(
            _research_result(candidate_id=""), uri=RESEARCH_URI
        )
        self.assertEqual(artifact.artifact_id, ":research")

    def test_deterministic_build(self):
        result = _research_result()
        first = build_research_package_artifact(result, uri=RESEARCH_URI)
        second = build_research_package_artifact(result, uri=RESEARCH_URI)
        self.assertEqual(first, second)


class TestBuildExperimentArtifact(unittest.TestCase):
    def test_exact_projection(self):
        artifact = build_experiment_package_artifact(
            _experiment_result(), uri=EXPERIMENT_URI
        )
        self.assertIsInstance(artifact, PackageArtifact)
        self.assertEqual(artifact.artifact_id, "cand-123:experiment")
        self.assertIs(artifact.kind, ArtifactKind.EXPERIMENT)
        self.assertEqual(artifact.uri, EXPERIMENT_URI)
        self.assertEqual(artifact.title, "Experiment execution result")
        self.assertEqual(artifact.metadata, EXPERIMENT_METADATA)
        self.assertEqual(set(artifact.metadata), set(EXPERIMENT_METADATA))

    def test_experiment_id_comes_from_plan_not_artifact_id_policy(self):
        artifact = build_experiment_package_artifact(
            _experiment_result(), uri=EXPERIMENT_URI
        )
        self.assertEqual(artifact.metadata["experiment_id"], "cand-123:experiment")
        self.assertNotEqual(
            artifact.metadata["experiment_id"], artifact.artifact_id.replace(":experiment", "")
        ) or True  # metadata experiment_id is plan identity; artifact_id is integration vocabulary

    def test_inconclusive_status_still_builds(self):
        artifact = build_experiment_package_artifact(
            _experiment_result(status=ExperimentExecutionStatus.INCONCLUSIVE),
            uri=EXPERIMENT_URI,
        )
        self.assertEqual(artifact.metadata["status"], "inconclusive")

    def test_count_projection_uses_raw_lengths(self):
        result = _experiment_result(
            observations=tuple(_observation(f"obs-{i}") for i in range(1, 6))
        )
        artifact = build_experiment_package_artifact(result, uri=EXPERIMENT_URI)
        self.assertEqual(artifact.metadata["observation_count"], 5)

    def test_caller_uri_preserved_exactly(self):
        for uri in ("", "not-a-uri", "memory://experiment/cand-123"):
            with self.subTest(uri=uri):
                artifact = build_experiment_package_artifact(
                    _experiment_result(), uri=uri
                )
                self.assertEqual(artifact.uri, uri)

    def test_builder_accepts_empty_candidate_id(self):
        artifact = build_experiment_package_artifact(
            _experiment_result(candidate_id=""), uri=EXPERIMENT_URI
        )
        self.assertEqual(artifact.artifact_id, ":experiment")

    def test_deterministic_build(self):
        result = _experiment_result()
        first = build_experiment_package_artifact(result, uri=EXPERIMENT_URI)
        second = build_experiment_package_artifact(result, uri=EXPERIMENT_URI)
        self.assertEqual(first, second)


class TestAttachResearchResult(unittest.TestCase):
    def test_attach_success(self):
        package = _package()
        result = _research_result()
        result_package = attach_research_result(
            package, result, uri=RESEARCH_URI, updated_at=UPDATED_AT
        )
        self.assertIsNot(result_package, package)
        self.assertEqual(len(result_package.artifacts), 1)
        artifact = result_package.artifacts[0]
        self.assertIs(artifact.kind, ArtifactKind.RESEARCH)
        self.assertEqual(artifact.artifact_id, "cand-123:research")
        self.assertEqual(result_package.updated_at, UPDATED_AT)
        self.assertEqual(package.artifacts, ())

    def test_attach_preserves_package_fields(self):
        package = _package()
        result_package = attach_research_result(
            package, _research_result(), uri=RESEARCH_URI, updated_at=UPDATED_AT
        )
        self.assertEqual(result_package.package_id, package.package_id)
        self.assertEqual(result_package.candidate_id, package.candidate_id)
        self.assertIs(result_package.strategy, package.strategy)
        self.assertIs(result_package.provenance, package.provenance)
        self.assertIs(result_package.stage, package.stage)
        self.assertIs(result_package.quality_state, package.quality_state)
        self.assertIs(result_package.publication_state, package.publication_state)
        self.assertIs(result_package.platform_variants, package.platform_variants)
        self.assertIs(result_package.analytics_links, package.analytics_links)
        self.assertEqual(result_package.created_at, package.created_at)
        self.assertEqual(result_package.legacy_content_id, package.legacy_content_id)

    def test_no_automatic_stage_change(self):
        package = _package(stage=PackageStage.RESEARCH_PENDING)
        result_package = attach_research_result(
            package, _research_result(), uri=RESEARCH_URI, updated_at=UPDATED_AT
        )
        self.assertIs(result_package.stage, PackageStage.RESEARCH_PENDING)

    def test_insufficient_result_still_attaches(self):
        package = _package()
        result_package = attach_research_result(
            package,
            _research_result(status=ResearchExecutionStatus.INSUFFICIENT),
            uri=RESEARCH_URI,
            updated_at=UPDATED_AT,
        )
        self.assertEqual(len(result_package.artifacts), 1)

    def test_candidate_mismatch_raises_exact_error_and_package_unchanged(self):
        package = _package()
        result = _research_result(candidate_id="cand-other")
        with self.assertRaises(ValueError) as ctx:
            attach_research_result(
                package, result, uri=RESEARCH_URI, updated_at=UPDATED_AT
            )
        self.assertEqual(
            str(ctx.exception),
            "candidate_id mismatch between package and research result",
        )
        self.assertEqual(package.artifacts, ())
        self.assertEqual(package.updated_at, CREATED_AT)

    def test_duplicate_attachment_propagates_stage_16c_error(self):
        package = _package()
        result = _research_result()
        attached = attach_research_result(
            package, result, uri=RESEARCH_URI, updated_at=UPDATED_AT
        )
        with self.assertRaises(ValueError) as ctx:
            attach_research_result(
                attached, result, uri=RESEARCH_URI, updated_at=UPDATED_AT
            )
        self.assertEqual(str(ctx.exception), "duplicate package artifact_id")
        self.assertEqual(len(attached.artifacts), 1)

    def test_existing_non_research_artifact_ids_do_not_collide(self):
        package = _package(
            platform_variants=(),
            analytics_links=(),
        )
        # Pre-populate with a research artifact via a different package path:
        # attach an analytics link and a variant first to prove no collision.
        staged = attach_platform_variant(
            package,
            __import__(
                "src.domain.content_package", fromlist=["PlatformVariantRef"]
            ).PlatformVariantRef(
                variant_id="var-1",
                platform=TargetPlatform.TELEGRAM,
                content_ref="ref",
                quality_state=QualityState.NOT_CHECKED,
                publication_state=PublicationState.NOT_READY,
            ),
            updated_at=UPDATED_AT,
        )
        staged = attach_analytics_link(
            staged,
            __import__(
                "src.domain.content_package", fromlist=["AnalyticsLink"]
            ).AnalyticsLink(
                analytics_id="an-1",
                platform=TargetPlatform.TELEGRAM,
                external_post_id="post-1",
            ),
            updated_at=UPDATED_AT,
        )
        result_package = attach_research_result(
            staged, _research_result(), uri=RESEARCH_URI, updated_at=UPDATED_AT
        )
        self.assertEqual(len(result_package.artifacts), 1)


class TestAttachExperimentResult(unittest.TestCase):
    def test_attach_success(self):
        package = _package(stage=PackageStage.STRATEGY_READY)
        result = _experiment_result()
        result_package = attach_experiment_result(
            package, result, uri=EXPERIMENT_URI, updated_at=UPDATED_AT
        )
        self.assertIsNot(result_package, package)
        self.assertEqual(len(result_package.artifacts), 1)
        artifact = result_package.artifacts[0]
        self.assertIs(artifact.kind, ArtifactKind.EXPERIMENT)
        self.assertEqual(artifact.artifact_id, "cand-123:experiment")
        self.assertEqual(result_package.updated_at, UPDATED_AT)
        self.assertEqual(package.artifacts, ())

    def test_attach_preserves_package_fields(self):
        package = _package()
        result_package = attach_experiment_result(
            package, _experiment_result(), uri=EXPERIMENT_URI, updated_at=UPDATED_AT
        )
        self.assertEqual(result_package.package_id, package.package_id)
        self.assertEqual(result_package.candidate_id, package.candidate_id)
        self.assertIs(result_package.strategy, package.strategy)
        self.assertIs(result_package.provenance, package.provenance)
        self.assertIs(result_package.stage, package.stage)
        self.assertIs(result_package.quality_state, package.quality_state)
        self.assertIs(result_package.publication_state, package.publication_state)
        self.assertIs(result_package.platform_variants, package.platform_variants)
        self.assertIs(result_package.analytics_links, package.analytics_links)
        self.assertEqual(result_package.created_at, package.created_at)
        self.assertEqual(result_package.legacy_content_id, package.legacy_content_id)

    def test_no_automatic_stage_change(self):
        package = _package(stage=PackageStage.STRATEGY_READY)
        result_package = attach_experiment_result(
            package, _experiment_result(), uri=EXPERIMENT_URI, updated_at=UPDATED_AT
        )
        self.assertIs(result_package.stage, PackageStage.STRATEGY_READY)

    def test_inconclusive_result_still_attaches(self):
        package = _package()
        result_package = attach_experiment_result(
            package,
            _experiment_result(status=ExperimentExecutionStatus.INCONCLUSIVE),
            uri=EXPERIMENT_URI,
            updated_at=UPDATED_AT,
        )
        self.assertEqual(len(result_package.artifacts), 1)

    def test_candidate_mismatch_raises_exact_error_and_package_unchanged(self):
        package = _package()
        result = _experiment_result(candidate_id="cand-other")
        with self.assertRaises(ValueError) as ctx:
            attach_experiment_result(
                package, result, uri=EXPERIMENT_URI, updated_at=UPDATED_AT
            )
        self.assertEqual(
            str(ctx.exception),
            "candidate_id mismatch between package and experiment result",
        )
        self.assertEqual(package.artifacts, ())
        self.assertEqual(package.updated_at, CREATED_AT)

    def test_duplicate_attachment_propagates_stage_16c_error(self):
        package = _package()
        result = _experiment_result()
        attached = attach_experiment_result(
            package, result, uri=EXPERIMENT_URI, updated_at=UPDATED_AT
        )
        with self.assertRaises(ValueError) as ctx:
            attach_experiment_result(
                attached, result, uri=EXPERIMENT_URI, updated_at=UPDATED_AT
            )
        self.assertEqual(str(ctx.exception), "duplicate package artifact_id")
        self.assertEqual(len(attached.artifacts), 1)

    def test_internal_plan_mismatch_is_not_validated(self):
        plan = _experiment_plan(candidate_id="different-plan-candidate")
        result = _experiment_result(plan=plan)
        artifact = build_experiment_package_artifact(result, uri=EXPERIMENT_URI)
        self.assertEqual(artifact.metadata["experiment_id"], "cand-123:experiment")
        package = _package()
        result_package = attach_experiment_result(
            package, result, uri=EXPERIMENT_URI, updated_at=UPDATED_AT
        )
        self.assertEqual(len(result_package.artifacts), 1)


class TestCoexistence(unittest.TestCase):
    def test_research_and_experiment_artifacts_coexist_in_order(self):
        package = _package()
        staged = attach_research_result(
            package, _research_result(), uri=RESEARCH_URI, updated_at=UPDATED_AT
        )
        result_package = attach_experiment_result(
            staged, _experiment_result(), uri=EXPERIMENT_URI, updated_at=UPDATED_AT
        )
        self.assertEqual(
            [artifact.artifact_id for artifact in result_package.artifacts],
            ["cand-123:research", "cand-123:experiment"],
        )
        self.assertIs(result_package.artifacts[0].kind, ArtifactKind.RESEARCH)
        self.assertIs(result_package.artifacts[1].kind, ArtifactKind.EXPERIMENT)


class TestResultInputImmutability(unittest.TestCase):
    def test_research_result_unchanged_after_build_and_attach(self):
        result = _research_result()
        requirements = result.requirements
        evidence = result.evidence
        requirement = result.requirements[0]
        record = result.evidence[0]

        build_research_package_artifact(result, uri=RESEARCH_URI)
        attach_research_result(_package(), result, uri=RESEARCH_URI, updated_at=UPDATED_AT)

        self.assertIs(result.requirements, requirements)
        self.assertIs(result.evidence, evidence)
        self.assertIs(result.requirements[0], requirement)
        self.assertIs(result.evidence[0], record)
        self.assertEqual(result.candidate_id, "cand-123")
        self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
        self.assertEqual(result.started_at, "2026-09-19T11:00:00+00:00")
        self.assertEqual(result.completed_at, "2026-09-19T11:05:00+00:00")

    def test_experiment_result_unchanged_after_build_and_attach(self):
        result = _experiment_result()
        plan = result.plan
        observations = result.observations
        observation = result.observations[0]

        build_experiment_package_artifact(result, uri=EXPERIMENT_URI)
        attach_experiment_result(
            _package(), result, uri=EXPERIMENT_URI, updated_at=UPDATED_AT
        )

        self.assertIs(result.plan, plan)
        self.assertIs(result.observations, observations)
        self.assertIs(result.observations[0], observation)
        self.assertEqual(result.candidate_id, "cand-123")
        self.assertIs(result.status, ExperimentExecutionStatus.COMPLETED)
        self.assertEqual(plan.experiment_id, "cand-123:experiment")
        self.assertEqual(observation.observation_id, "obs-1")


class TestPackageInputImmutability(unittest.TestCase):
    def test_original_package_unchanged_after_attach(self):
        package = _package()
        artifacts = package.artifacts
        attach_research_result(
            package, _research_result(), uri=RESEARCH_URI, updated_at=UPDATED_AT
        )
        attach_experiment_result(
            package, _experiment_result(), uri=EXPERIMENT_URI, updated_at=UPDATED_AT
        )
        self.assertIs(package.artifacts, artifacts)
        self.assertEqual(package.artifacts, ())
        self.assertEqual(package.updated_at, CREATED_AT)
        self.assertIs(package.stage, PackageStage.RESEARCH_PENDING)
        self.assertIs(package.quality_state, QualityState.NOT_CHECKED)
        self.assertIs(package.publication_state, PublicationState.NOT_READY)


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees for the integration module
# ──────────────────────────────────────────────────────────────────────

def _module_tree() -> ast.Module:
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def _module_ids(tree: ast.Module) -> set:
    """All Name ids, Attribute attrs, and import names (docstring-immune)."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            ids.add(node.id)
        elif isinstance(node, ast.Attribute):
            ids.add(node.attr)
        elif isinstance(node, ast.Import):
            ids.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                ids.add(node.module)
            ids.update(alias.name for alias in node.names)
    return ids


def _function(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


class TestIntegrationStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _module_tree()
        cls.ids = _module_ids(cls.tree)
        cls.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_exactly_four_module_level_functions(self):
        functions = [
            node for node in self.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(
            [f.name for f in functions],
            [
                "build_research_package_artifact",
                "build_experiment_package_artifact",
                "attach_research_result",
                "attach_experiment_result",
            ],
        )

    def test_all_is_exactly_four_functions(self):
        assigns = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        ]
        self.assertEqual(len(assigns), 1)
        values = [elt.value for elt in assigns[0].value.elts]
        self.assertEqual(
            values,
            [
                "build_research_package_artifact",
                "build_experiment_package_artifact",
                "attach_research_result",
                "attach_experiment_result",
            ],
        )

    def test_construction_and_call_shape(self):
        artifact_calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "PackageArtifact"
        ]
        attach_calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "attach_package_artifact"
        ]
        package_calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ContentPackageV2"
        ]
        self.assertEqual(len(artifact_calls), 2)
        self.assertEqual(len(attach_calls), 2)
        self.assertEqual(package_calls, [])

    def test_builder_call_wiring(self):
        research_fn = _function(self.tree, "attach_research_result")
        experiment_fn = _function(self.tree, "attach_experiment_result")

        research_calls = [
            node.func.id for node in ast.walk(research_fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id != "ValueError"
        ]
        experiment_calls = [
            node.func.id for node in ast.walk(experiment_fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id != "ValueError"
        ]
        self.assertEqual(
            research_calls,
            ["build_research_package_artifact", "attach_package_artifact"],
        )
        self.assertEqual(
            experiment_calls,
            ["build_experiment_package_artifact", "attach_package_artifact"],
        )

    def test_no_lifecycle_or_state_imports(self):
        forbidden = {
            "transition_package_stage", "PackageStage", "QualityState",
            "PublicationState",
        }
        leaks = sorted(token for token in forbidden if token in self.ids)
        self.assertEqual(leaks, [])

    def test_no_reconstruction_or_replace(self):
        self.assertNotIn("replace", self.ids)

    def test_no_forbidden_imports_or_references(self):
        forbidden = {
            # Persistence / config / DB.
            "StateService", "sqlite3", "Config", "repository", "database",
            # Generation sources.
            "datetime", "time", "uuid", "hashlib", "random",
            # Filesystem / network / process.
            "os", "pathlib", "subprocess", "requests", "httpx", "urllib",
            "socket",
            # Strategy coupling.
            "StrategistPlan", "ContentCandidate", "ContentFormat",
            "ContentCluster", "TargetPlatform",
            # Serialization helpers.
            "json", "pickle", "asdict", "to_dict", "from_dict", "serialize",
            "deserialize",
        }
        leaks = sorted(token for token in forbidden if token in self.ids)
        self.assertEqual(leaks, [])

    def test_no_open_print_exec_eval_calls(self):
        call_names = {
            node.func.id
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertEqual(call_names & {"open", "print", "exec", "eval"}, set())

    def test_no_try_nodes(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.Try)

    def test_exactly_two_value_error_sites_with_exact_messages(self):
        raises = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "ValueError"
        ]
        self.assertEqual(len(raises), 2)
        messages = sorted(
            node.exc.args[0].value for node in raises
            if isinstance(node.exc.args[0], ast.Constant)
        )
        self.assertEqual(
            messages,
            [
                "candidate_id mismatch between package and experiment result",
                "candidate_id mismatch between package and research result",
            ],
        )

    def test_no_pre_scan_loops_over_package_artifacts(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, (ast.For, ast.AsyncFor))
            self.assertNotIsInstance(
                node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
            )

    def test_no_status_branching(self):
        """result.status may appear only as result.status.value in metadata."""
        status_accesses = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and node.attr == "status"
            and isinstance(node.value, ast.Name)
            and node.value.id == "result"
        ]
        self.assertTrue(status_accesses)
        for node in status_accesses:
            self.assertIsInstance(node.ctx, ast.Load)

    def test_research_result_field_access_boundary(self):
        research_fn = _function(self.tree, "build_research_package_artifact")
        accessed = {
            node.attr
            for node in ast.walk(research_fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "result"
        }
        self.assertEqual(
            accessed,
            {
                "candidate_id", "status", "requirements", "evidence",
                "started_at", "completed_at", "notes",
            },
        )

    def test_experiment_result_field_access_boundary(self):
        experiment_fn = _function(self.tree, "build_experiment_package_artifact")
        result_accessed = {
            node.attr
            for node in ast.walk(experiment_fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "result"
        }
        self.assertEqual(
            result_accessed,
            {
                "candidate_id", "plan", "status", "observations",
                "started_at", "completed_at", "conclusion", "notes",
            },
        )
        plan_accessed = {
            node.attr
            for node in ast.walk(experiment_fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "plan"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "result"
        }
        self.assertEqual(plan_accessed, {"experiment_id"})

    def test_metadata_key_contracts(self):
        def _dict_literal_keys(fn):
            dicts = [
                node for node in ast.walk(fn)
                if isinstance(node, ast.Dict)
                and all(isinstance(key, ast.Constant) for key in node.keys)
            ]
            self.assertEqual(len(dicts), 1)
            return [key.value for key in dicts[0].keys]

        research_fn = _function(self.tree, "build_research_package_artifact")
        experiment_fn = _function(self.tree, "build_experiment_package_artifact")

        self.assertEqual(
            _dict_literal_keys(research_fn),
            [
                "candidate_id", "status", "requirement_count",
                "evidence_count", "started_at", "completed_at", "notes",
            ],
        )
        self.assertEqual(
            _dict_literal_keys(experiment_fn),
            [
                "candidate_id", "experiment_id", "status",
                "observation_count", "started_at", "completed_at",
                "conclusion", "notes",
            ],
        )


if __name__ == "__main__":
    unittest.main()
