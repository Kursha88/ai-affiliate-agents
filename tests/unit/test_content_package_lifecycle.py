"""Step 16C unit tests: immutable ContentPackageV2 enrichment and lifecycle.

Covers append-only attachment of artifacts, platform-variant refs and
analytics links (duplicate-ID rejection, ID-only semantics, append order,
identity preservation), the explicit stage transition graph (all normal
forward transitions, MANUAL_REVIEW, terminal states, self/skip rejection),
caller-supplied updated_at, non-coupling between enrichment and lifecycle,
and structural AST guarantees (dataclasses.replace only, exact keyword
sets, full transition map, no side-effect coupling). Fixtures construct
ContentPackageV2 directly: build_content_package() is deliberately NOT
used so this suite isolates the 16C boundary.
"""

import ast
import unittest
from pathlib import Path

from src.content.content_package_lifecycle import (
    attach_analytics_link,
    attach_package_artifact,
    attach_platform_variant,
    transition_package_stage,
)
from src.domain.content_package import (
    AnalyticsLink,
    ArtifactKind,
    ContentPackageV2,
    PackageArtifact,
    PackageStage,
    PlatformVariantRef,
    PublicationState,
    QualityState,
    SourceProvenance,
)
from src.domain.strategy import ContentCluster, ContentFormat, TargetPlatform
from src.domain.strategist import StrategistPlan

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "content"
    / "content_package_lifecycle.py"
)

CREATED_AT = "2026-09-19T10:10:00+00:00"
BASE_UPDATED_AT = "2026-09-19T10:10:00+00:00"


def _plan(**overrides) -> StrategistPlan:
    defaults = dict(
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
        structure=("problem", "tool", "cta"),
        language="ru",
        mode="growth",
    )
    defaults.update(overrides)
    return StrategistPlan(**defaults)


PROVENANCE = SourceProvenance(
    candidate_id="cand-123",
    source_url="https://example.com/tool",
    source_name="example",
    source_type="github",
    discovered_at="2026-09-19T10:00:00+00:00",
    published_at="2026-09-19T09:00:00+00:00",
    verification_status="verified",
    verification_confidence=0.91,
)


def _package(**overrides) -> ContentPackageV2:
    defaults = dict(
        package_id="pkg-123",
        candidate_id="cand-123",
        strategy=_plan(),
        provenance=PROVENANCE,
        stage=PackageStage.STRATEGY_READY,
        quality_state=QualityState.NOT_CHECKED,
        publication_state=PublicationState.NOT_READY,
        artifacts=(),
        platform_variants=(),
        analytics_links=(),
        created_at=CREATED_AT,
        updated_at=BASE_UPDATED_AT,
        legacy_content_id=None,
    )
    defaults.update(overrides)
    return ContentPackageV2(**defaults)


def _artifact(artifact_id="artifact-1", **overrides) -> PackageArtifact:
    defaults = dict(
        artifact_id=artifact_id,
        kind=ArtifactKind.RESEARCH,
        uri="memory://research/1",
        title="Research evidence",
        metadata={"source": "test"},
    )
    defaults.update(overrides)
    return PackageArtifact(**defaults)


def _variant(variant_id="variant-1", **overrides) -> PlatformVariantRef:
    defaults = dict(
        variant_id=variant_id,
        platform=TargetPlatform.TELEGRAM,
        content_ref="memory://variant/1",
        quality_state=QualityState.NOT_CHECKED,
        publication_state=PublicationState.NOT_READY,
    )
    defaults.update(overrides)
    return PlatformVariantRef(**defaults)


def _analytics(analytics_id="analytics-1", **overrides) -> AnalyticsLink:
    defaults = dict(
        analytics_id=analytics_id,
        platform=TargetPlatform.TELEGRAM,
        external_post_id="post-123",
    )
    defaults.update(overrides)
    return AnalyticsLink(**defaults)


NEW_UPDATED_AT = "2026-09-19T11:00:00+00:00"


class TestAttachPackageArtifact(unittest.TestCase):
    def setUp(self):
        self.package = _package()
        self.artifact = _artifact()
        self.result = attach_package_artifact(
            self.package, self.artifact, updated_at=NEW_UPDATED_AT
        )

    def test_returns_content_package_v2(self):
        self.assertIsInstance(self.result, ContentPackageV2)

    def test_returns_new_package_object(self):
        self.assertIsNot(self.result, self.package)

    def test_original_artifacts_unchanged(self):
        self.assertEqual(self.package.artifacts, ())

    def test_result_artifacts_single_exact_object(self):
        self.assertEqual(self.result.artifacts, (self.artifact,))
        self.assertIs(self.result.artifacts[0], self.artifact)

    def test_updated_at_exact(self):
        self.assertEqual(self.result.updated_at, NEW_UPDATED_AT)

    def test_stage_unchanged(self):
        self.assertIs(self.result.stage, self.package.stage)

    def test_quality_state_unchanged(self):
        self.assertIs(self.result.quality_state, QualityState.NOT_CHECKED)

    def test_publication_state_unchanged(self):
        self.assertIs(self.result.publication_state, PublicationState.NOT_READY)

    def test_strategy_identity_preserved(self):
        self.assertIs(self.result.strategy, self.package.strategy)

    def test_provenance_identity_preserved(self):
        self.assertIs(self.result.provenance, self.package.provenance)

    def test_platform_variants_tuple_identity_preserved(self):
        self.assertIs(self.result.platform_variants, self.package.platform_variants)

    def test_analytics_links_tuple_identity_preserved(self):
        self.assertIs(self.result.analytics_links, self.package.analytics_links)

    def test_created_at_unchanged(self):
        self.assertEqual(self.result.created_at, self.package.created_at)

    def test_package_and_candidate_id_unchanged(self):
        self.assertEqual(self.result.package_id, self.package.package_id)
        self.assertEqual(self.result.candidate_id, self.package.candidate_id)

    def test_legacy_content_id_unchanged(self):
        self.assertIs(self.result.legacy_content_id, self.package.legacy_content_id)

    def test_append_order_preserved(self):
        artifact_1 = _artifact(artifact_id="artifact-1")
        artifact_2 = _artifact(artifact_id="artifact-2", kind=ArtifactKind.EXPERIMENT)
        staged = attach_package_artifact(
            self.package, artifact_1, updated_at=NEW_UPDATED_AT
        )
        result = attach_package_artifact(staged, artifact_2, updated_at=NEW_UPDATED_AT)
        self.assertEqual(result.artifacts, (artifact_1, artifact_2))
        self.assertIs(result.artifacts[0], artifact_1)
        self.assertIs(result.artifacts[1], artifact_2)

    def test_duplicate_artifact_id_rejected_with_original_unchanged(self):
        staged = attach_package_artifact(
            self.package, _artifact(artifact_id="artifact-1"), updated_at=NEW_UPDATED_AT
        )
        duplicate = _artifact(
            artifact_id="artifact-1",
            kind=ArtifactKind.IMAGE,
            uri="memory://image/other",
            title="Different title",
            metadata={"different": True},
        )
        with self.assertRaises(ValueError) as ctx:
            attach_package_artifact(staged, duplicate, updated_at=NEW_UPDATED_AT)
        self.assertEqual(str(ctx.exception), "duplicate package artifact_id")
        self.assertEqual(len(staged.artifacts), 1)
        self.assertEqual(self.package.artifacts, ())

    def test_distinct_id_with_identical_data_allowed(self):
        first = _artifact(artifact_id="artifact-1")
        second = _artifact(artifact_id="artifact-2")  # identical data, distinct ID
        staged = attach_package_artifact(
            self.package, first, updated_at=NEW_UPDATED_AT
        )
        result = attach_package_artifact(staged, second, updated_at=NEW_UPDATED_AT)
        self.assertEqual(len(result.artifacts), 2)

    def test_empty_updated_at_accepted(self):
        result = attach_package_artifact(self.package, self.artifact, updated_at="")
        self.assertEqual(result.updated_at, "")

    def test_no_automatic_stage_change_when_attaching(self):
        package = _package(stage=PackageStage.RESEARCH_PENDING)
        result = attach_package_artifact(package, self.artifact, updated_at=NEW_UPDATED_AT)
        self.assertIs(result.stage, PackageStage.RESEARCH_PENDING)


class TestAttachPlatformVariant(unittest.TestCase):
    def setUp(self):
        self.package = _package()
        self.variant = _variant()
        self.result = attach_platform_variant(
            self.package, self.variant, updated_at=NEW_UPDATED_AT
        )

    def test_returns_new_package_with_exact_variant(self):
        self.assertIsInstance(self.result, ContentPackageV2)
        self.assertIsNot(self.result, self.package)
        self.assertEqual(self.result.platform_variants, (self.variant,))
        self.assertIs(self.result.platform_variants[0], self.variant)

    def test_updated_at_exact(self):
        self.assertEqual(self.result.updated_at, NEW_UPDATED_AT)

    def test_stage_quality_publication_unchanged(self):
        self.assertIs(self.result.stage, self.package.stage)
        self.assertIs(self.result.quality_state, QualityState.NOT_CHECKED)
        self.assertIs(self.result.publication_state, PublicationState.NOT_READY)

    def test_strategy_provenance_identity_preserved(self):
        self.assertIs(self.result.strategy, self.package.strategy)
        self.assertIs(self.result.provenance, self.package.provenance)

    def test_unrelated_tuple_identities_preserved(self):
        self.assertIs(self.result.artifacts, self.package.artifacts)
        self.assertIs(self.result.analytics_links, self.package.analytics_links)

    def test_created_at_ids_legacy_unchanged(self):
        self.assertEqual(self.result.created_at, self.package.created_at)
        self.assertEqual(self.result.package_id, self.package.package_id)
        self.assertEqual(self.result.candidate_id, self.package.candidate_id)
        self.assertIs(self.result.legacy_content_id, self.package.legacy_content_id)

    def test_append_order_preserved(self):
        variant_1 = _variant(variant_id="variant-1")
        variant_2 = _variant(variant_id="variant-2", platform=TargetPlatform.X)
        staged = attach_platform_variant(
            self.package, variant_1, updated_at=NEW_UPDATED_AT
        )
        result = attach_platform_variant(staged, variant_2, updated_at=NEW_UPDATED_AT)
        self.assertEqual(result.platform_variants, (variant_1, variant_2))
        self.assertIs(result.platform_variants[0], variant_1)
        self.assertIs(result.platform_variants[1], variant_2)

    def test_duplicate_variant_id_rejected_with_original_unchanged(self):
        staged = attach_platform_variant(
            self.package, _variant(variant_id="variant-1"), updated_at=NEW_UPDATED_AT
        )
        duplicate = _variant(
            variant_id="variant-1",
            platform=TargetPlatform.X,
            content_ref="memory://variant/other",
        )
        with self.assertRaises(ValueError) as ctx:
            attach_platform_variant(staged, duplicate, updated_at=NEW_UPDATED_AT)
        self.assertEqual(str(ctx.exception), "duplicate platform variant_id")
        self.assertEqual(len(staged.platform_variants), 1)
        self.assertEqual(self.package.platform_variants, ())

    def test_same_platform_with_different_ids_allowed(self):
        variant_1 = _variant(variant_id="variant-1", platform=TargetPlatform.TELEGRAM)
        variant_2 = _variant(variant_id="variant-2", platform=TargetPlatform.TELEGRAM)
        staged = attach_platform_variant(
            self.package, variant_1, updated_at=NEW_UPDATED_AT
        )
        result = attach_platform_variant(staged, variant_2, updated_at=NEW_UPDATED_AT)
        self.assertEqual(result.platform_variants, (variant_1, variant_2))
        self.assertIs(result.platform_variants[0].platform, TargetPlatform.TELEGRAM)
        self.assertIs(result.platform_variants[1].platform, TargetPlatform.TELEGRAM)

    def test_distinct_id_with_identical_data_allowed(self):
        first = _variant(variant_id="variant-1")
        second = _variant(variant_id="variant-2")
        staged = attach_platform_variant(
            self.package, first, updated_at=NEW_UPDATED_AT
        )
        result = attach_platform_variant(staged, second, updated_at=NEW_UPDATED_AT)
        self.assertEqual(len(result.platform_variants), 2)

    def test_empty_updated_at_accepted(self):
        result = attach_platform_variant(self.package, self.variant, updated_at="")
        self.assertEqual(result.updated_at, "")

    def test_no_automatic_stage_change_when_attaching(self):
        package = _package(stage=PackageStage.ADAPTATION_PENDING)
        result = attach_platform_variant(package, self.variant, updated_at=NEW_UPDATED_AT)
        self.assertIs(result.stage, PackageStage.ADAPTATION_PENDING)


class TestAttachAnalyticsLink(unittest.TestCase):
    def setUp(self):
        self.package = _package()
        self.analytics = _analytics()
        self.result = attach_analytics_link(
            self.package, self.analytics, updated_at=NEW_UPDATED_AT
        )

    def test_returns_new_package_with_exact_link(self):
        self.assertIsInstance(self.result, ContentPackageV2)
        self.assertIsNot(self.result, self.package)
        self.assertEqual(self.result.analytics_links, (self.analytics,))
        self.assertIs(self.result.analytics_links[0], self.analytics)

    def test_updated_at_exact(self):
        self.assertEqual(self.result.updated_at, NEW_UPDATED_AT)

    def test_stage_quality_publication_unchanged(self):
        self.assertIs(self.result.stage, self.package.stage)
        self.assertIs(self.result.quality_state, QualityState.NOT_CHECKED)
        self.assertIs(self.result.publication_state, PublicationState.NOT_READY)

    def test_strategy_provenance_identity_preserved(self):
        self.assertIs(self.result.strategy, self.package.strategy)
        self.assertIs(self.result.provenance, self.package.provenance)

    def test_unrelated_tuple_identities_preserved(self):
        self.assertIs(self.result.artifacts, self.package.artifacts)
        self.assertIs(self.result.platform_variants, self.package.platform_variants)

    def test_append_order_preserved(self):
        first = _analytics(analytics_id="analytics-1")
        second = _analytics(analytics_id="analytics-2", external_post_id="post-456")
        staged = attach_analytics_link(self.package, first, updated_at=NEW_UPDATED_AT)
        result = attach_analytics_link(staged, second, updated_at=NEW_UPDATED_AT)
        self.assertEqual(result.analytics_links, (first, second))
        self.assertIs(result.analytics_links[0], first)
        self.assertIs(result.analytics_links[1], second)

    def test_duplicate_analytics_id_rejected_with_original_unchanged(self):
        staged = attach_analytics_link(
            self.package, _analytics(analytics_id="analytics-1"), updated_at=NEW_UPDATED_AT
        )
        duplicate = _analytics(analytics_id="analytics-1", external_post_id="other")
        with self.assertRaises(ValueError) as ctx:
            attach_analytics_link(staged, duplicate, updated_at=NEW_UPDATED_AT)
        self.assertEqual(str(ctx.exception), "duplicate analytics_id")
        self.assertEqual(len(staged.analytics_links), 1)
        self.assertEqual(self.package.analytics_links, ())

    def test_distinct_id_with_identical_data_allowed(self):
        first = _analytics(analytics_id="analytics-1")
        second = _analytics(analytics_id="analytics-2")
        staged = attach_analytics_link(self.package, first, updated_at=NEW_UPDATED_AT)
        result = attach_analytics_link(staged, second, updated_at=NEW_UPDATED_AT)
        self.assertEqual(len(result.analytics_links), 2)

    def test_empty_updated_at_accepted(self):
        result = attach_analytics_link(self.package, self.analytics, updated_at="")
        self.assertEqual(result.updated_at, "")

    def test_no_automatic_stage_change_when_attaching(self):
        package = _package(stage=PackageStage.PUBLISHED)
        result = attach_analytics_link(package, self.analytics, updated_at=NEW_UPDATED_AT)
        self.assertIs(result.stage, PackageStage.PUBLISHED)


NORMAL_TRANSITIONS = (
    (PackageStage.STRATEGY_READY, PackageStage.RESEARCH_PENDING),
    (PackageStage.STRATEGY_READY, PackageStage.CREATION_PENDING),
    (PackageStage.RESEARCH_PENDING, PackageStage.RESEARCH_READY),
    (PackageStage.RESEARCH_READY, PackageStage.CREATION_PENDING),
    (PackageStage.CREATION_PENDING, PackageStage.CONTENT_READY),
    (PackageStage.CONTENT_READY, PackageStage.ADAPTATION_PENDING),
    (PackageStage.ADAPTATION_PENDING, PackageStage.VARIANTS_READY),
    (PackageStage.VARIANTS_READY, PackageStage.QA_PENDING),
    (PackageStage.QA_PENDING, PackageStage.APPROVED),
    (PackageStage.APPROVED, PackageStage.PUBLISHING),
    (PackageStage.PUBLISHING, PackageStage.PUBLISHED),
    (PackageStage.PUBLISHED, PackageStage.ANALYZED),
    (PackageStage.ANALYZED, PackageStage.ARCHIVED),
)

MANUAL_REVIEW_SOURCES = (
    PackageStage.STRATEGY_READY,
    PackageStage.RESEARCH_PENDING,
    PackageStage.RESEARCH_READY,
    PackageStage.CREATION_PENDING,
    PackageStage.CONTENT_READY,
    PackageStage.ADAPTATION_PENDING,
    PackageStage.VARIANTS_READY,
    PackageStage.QA_PENDING,
    PackageStage.APPROVED,
    PackageStage.PUBLISHING,
    PackageStage.PUBLISHED,
    PackageStage.ANALYZED,
)


class TestTransitionPackageStage(unittest.TestCase):
    def test_all_normal_forward_transitions(self):
        for source, target in NORMAL_TRANSITIONS:
            with self.subTest(source=source.value, target=target.value):
                package = _package(stage=source)
                result = transition_package_stage(package, target, updated_at=NEW_UPDATED_AT)
                self.assertIsNot(result, package)
                self.assertIs(result.stage, target)
                self.assertEqual(result.updated_at, NEW_UPDATED_AT)
                self.assertIs(result.strategy, package.strategy)
                self.assertIs(result.provenance, package.provenance)
                self.assertIs(result.artifacts, package.artifacts)
                self.assertIs(result.platform_variants, package.platform_variants)
                self.assertIs(result.analytics_links, package.analytics_links)
                self.assertIs(result.quality_state, package.quality_state)
                self.assertIs(result.publication_state, package.publication_state)
                self.assertEqual(result.created_at, package.created_at)

    def test_manual_review_allowed_from_every_nonterminal_stage(self):
        for source in MANUAL_REVIEW_SOURCES:
            with self.subTest(source=source.value):
                package = _package(stage=source)
                result = transition_package_stage(
                    package, PackageStage.MANUAL_REVIEW, updated_at=NEW_UPDATED_AT
                )
                self.assertIs(result.stage, PackageStage.MANUAL_REVIEW)

    def test_archived_is_terminal(self):
        package = _package(stage=PackageStage.ARCHIVED)
        for target in PackageStage:
            with self.subTest(target=target.value):
                with self.assertRaises(ValueError) as ctx:
                    transition_package_stage(package, target, updated_at=NEW_UPDATED_AT)
                self.assertEqual(
                    str(ctx.exception),
                    f"invalid package stage transition: archived -> {target.value}",
                )

    def test_manual_review_is_terminal(self):
        package = _package(stage=PackageStage.MANUAL_REVIEW)
        for target in PackageStage:
            with self.subTest(target=target.value):
                with self.assertRaises(ValueError) as ctx:
                    transition_package_stage(package, target, updated_at=NEW_UPDATED_AT)
                self.assertEqual(
                    str(ctx.exception),
                    f"invalid package stage transition: manual_review -> {target.value}",
                )

    def test_self_transitions_rejected(self):
        for stage in (
            PackageStage.STRATEGY_READY,
            PackageStage.PUBLISHED,
            PackageStage.MANUAL_REVIEW,
        ):
            with self.subTest(stage=stage.value):
                package = _package(stage=stage)
                with self.assertRaises(ValueError) as ctx:
                    transition_package_stage(package, stage, updated_at=NEW_UPDATED_AT)
                self.assertEqual(
                    str(ctx.exception),
                    f"invalid package stage transition: {stage.value} -> {stage.value}",
                )

    def test_representative_skip_transitions_rejected(self):
        skips = (
            (PackageStage.STRATEGY_READY, PackageStage.CONTENT_READY),
            (PackageStage.RESEARCH_PENDING, PackageStage.CREATION_PENDING),
            (PackageStage.CREATION_PENDING, PackageStage.VARIANTS_READY),
            (PackageStage.CONTENT_READY, PackageStage.QA_PENDING),
            (PackageStage.QA_PENDING, PackageStage.PUBLISHING),
            (PackageStage.APPROVED, PackageStage.PUBLISHED),
            (PackageStage.PUBLISHED, PackageStage.ARCHIVED),
        )
        for source, target in skips:
            with self.subTest(source=source.value, target=target.value):
                package = _package(stage=source)
                with self.assertRaises(ValueError) as ctx:
                    transition_package_stage(package, target, updated_at=NEW_UPDATED_AT)
                self.assertEqual(
                    str(ctx.exception),
                    f"invalid package stage transition: {source.value} -> {target.value}",
                )

    def test_exact_error_message_format(self):
        package = _package(stage=PackageStage.STRATEGY_READY)
        with self.assertRaises(ValueError) as ctx:
            transition_package_stage(
                package, PackageStage.CONTENT_READY, updated_at=NEW_UPDATED_AT
            )
        self.assertEqual(
            str(ctx.exception),
            "invalid package stage transition: strategy_ready -> content_ready",
        )

    def test_transition_accepts_non_timestamp_updated_at(self):
        package = _package()
        result = transition_package_stage(
            package, PackageStage.RESEARCH_PENDING, updated_at="not-a-timestamp"
        )
        self.assertEqual(result.updated_at, "not-a-timestamp")

    def test_strategy_flags_do_not_restrict_lifecycle_graph(self):
        package = _package(
            strategy=_plan(research_required=True, experiment_required=True)
        )
        result = transition_package_stage(
            package, PackageStage.CREATION_PENDING, updated_at=NEW_UPDATED_AT
        )
        self.assertIs(result.stage, PackageStage.CREATION_PENDING)

    def test_transition_never_touches_quality_or_publication_states(self):
        package = _package(
            quality_state=QualityState.REJECTED,
            publication_state=PublicationState.FAILED,
        )
        result = transition_package_stage(
            package, PackageStage.RESEARCH_PENDING, updated_at=NEW_UPDATED_AT
        )
        self.assertIs(result.quality_state, QualityState.REJECTED)
        self.assertIs(result.publication_state, PublicationState.FAILED)


class TestNoQualityPublicationChangesOnAttach(unittest.TestCase):
    def test_attach_operations_never_repair_non_default_states(self):
        package = _package(
            quality_state=QualityState.REJECTED,
            publication_state=PublicationState.FAILED,
            stage=PackageStage.CONTENT_READY,
        )
        artifact_result = attach_package_artifact(
            package, _artifact(), updated_at=NEW_UPDATED_AT
        )
        variant_result = attach_platform_variant(
            package, _variant(), updated_at=NEW_UPDATED_AT
        )
        analytics_result = attach_analytics_link(
            package, _analytics(), updated_at=NEW_UPDATED_AT
        )
        transition_result = transition_package_stage(
            package, PackageStage.ADAPTATION_PENDING, updated_at=NEW_UPDATED_AT
        )
        for result in (artifact_result, variant_result, analytics_result, transition_result):
            with self.subTest(stage=result.stage.value):
                self.assertIs(result.quality_state, QualityState.REJECTED)
                self.assertIs(result.publication_state, PublicationState.FAILED)


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees for the lifecycle module
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


class TestLifecycleStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _module_tree()
        cls.ids = _module_ids(cls.tree)

    def _public_functions(self):
        return [
            node for node in self.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

    def _replace_calls_in_function(self, fn):
        return [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "replace"
        ]

    def test_exactly_four_module_level_functions(self):
        functions = self._public_functions()
        self.assertEqual(
            [f.name for f in functions],
            [
                "attach_package_artifact",
                "attach_platform_variant",
                "attach_analytics_link",
                "transition_package_stage",
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
                "attach_package_artifact",
                "attach_platform_variant",
                "attach_analytics_link",
                "transition_package_stage",
            ],
        )

    def test_imports_dataclasses_replace(self):
        found = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "dataclasses"
            and any(alias.name == "replace" for alias in node.names)
        ]
        self.assertEqual(len(found), 1)

    def test_no_direct_content_package_v2_construction(self):
        constructions = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ContentPackageV2"
        ]
        self.assertEqual(constructions, [])

    def test_exactly_one_replace_call_per_public_function(self):
        for fn in self._public_functions():
            with self.subTest(function=fn.name):
                calls = self._replace_calls_in_function(fn)
                self.assertEqual(len(calls), 1)

    def test_replace_keyword_sets_are_exact(self):
        expected = {
            "attach_package_artifact": {"artifacts", "updated_at"},
            "attach_platform_variant": {"platform_variants", "updated_at"},
            "attach_analytics_link": {"analytics_links", "updated_at"},
            "transition_package_stage": {"stage", "updated_at"},
        }
        forbidden = {
            "strategy", "provenance", "quality_state", "publication_state",
            "created_at", "package_id", "candidate_id", "legacy_content_id",
        }
        for fn in self._public_functions():
            with self.subTest(function=fn.name):
                calls = self._replace_calls_in_function(fn)
                self.assertEqual(len(calls), 1)
                keywords = {kw.arg for kw in calls[0].keywords if kw.arg is not None}
                self.assertEqual(keywords, expected[fn.name])
                self.assertEqual(keywords & forbidden, set())

    def test_no_forbidden_imports_or_references(self):
        forbidden = {
            # Rebuild / mutation helpers.
            "deepcopy", "copy",
            # Generation sources.
            "datetime", "time", "uuid", "hashlib", "random",
            # Persistence / config / DB.
            "StateService", "sqlite3", "Config",
            # Filesystem / network.
            "os", "pathlib", "requests", "httpx",
            # Social / publishing integrations.
            "publisher", "copywriter", "editor", "designer",
            "telegram", "x_client", "vk_client", "pinterest_client",
            # Orchestration / builder coupling.
            "run_strategist", "run_select_stage", "run_live_research",
            "build_content_package",
            # Forbidden quality/publication setters.
            "set_quality_state", "transition_quality_state",
            "set_publication_state", "transition_publication_state",
            "approve_package", "mark_published", "mark_failed",
            # Forbidden removal/update helpers.
            "remove_artifact", "replace_artifact", "update_artifact",
            "remove_variant", "replace_variant", "update_variant",
            "remove_analytics_link", "replace_analytics_link",
        }
        leaks = sorted(token for token in forbidden if token in self.ids)
        self.assertEqual(leaks, [])

    def test_no_open_or_print_calls(self):
        call_names = {
            node.func.id
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertEqual(call_names & {"open", "print"}, set())

    def test_allowed_stage_transitions_exists_with_full_key_coverage(self):
        assignments = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_ALLOWED_STAGE_TRANSITIONS"
                for t in node.targets
            )
        ]
        self.assertEqual(len(assignments), 1)
        mapping = assignments[0].value
        self.assertIsInstance(mapping, ast.Dict)
        keys = [
            key.attr for key in mapping.keys
            if isinstance(key, ast.Attribute) and isinstance(key.value, ast.Name)
            and key.value.id == "PackageStage"
        ]
        self.assertEqual(
            sorted(keys),
            sorted(stage.name for stage in PackageStage),
        )
        self.assertEqual(len(keys), len(set(keys)))

    def test_map_values_are_tuple_literals(self):
        assignments = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_ALLOWED_STAGE_TRANSITIONS"
                for t in node.targets
            )
        ]
        for value in assignments[0].value.values:
            self.assertIsInstance(value, ast.Tuple)

    def test_archived_and_manual_review_map_to_empty_tuples(self):
        assignments = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_ALLOWED_STAGE_TRANSITIONS"
                for t in node.targets
            )
        ]
        mapping = assignments[0].value
        terminal = {}
        for key, value in zip(mapping.keys, mapping.values):
            if isinstance(key, ast.Attribute) and key.attr in ("ARCHIVED", "MANUAL_REVIEW"):
                terminal[key.attr] = value
        self.assertEqual(set(terminal), {"ARCHIVED", "MANUAL_REVIEW"})
        for attr, value in terminal.items():
            self.assertIsInstance(value, ast.Tuple)
            self.assertEqual(value.elts, [])


if __name__ == "__main__":
    unittest.main()
