"""Step 16A unit tests: Content Package 2.0 domain contracts.

Binds the src.domain.content_package contracts to their intended shape:
exact enum vocabularies, frozen dataclasses with exact field order and no
defaults, identity preservation of nested strategy/provenance/tuples, and
the absence of any methods, builders, serialization, validation, state
machine, persistence, or I/O coupling. The legacy Stage 3.1
``src.domain.strategy.ContentPackage`` must remain a separate type.
"""

import ast
import dataclasses
import unittest
from pathlib import Path
from unittest import mock  # noqa: F401  (unused; keeps unittest-only harness explicit)

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
from src.domain.strategy import (
    ContentCluster,
    ContentFormat,
    TargetPlatform,
)
from src.domain.strategist import StrategistPlan

MODULE_PATH = Path(__file__).resolve().parents[2] / "src" / "domain" / "content_package.py"

PLAN_STRUCTURE = ("hook", "prerequisites", "steps", "result", "cta")

STRATEGIST_PLAN = StrategistPlan(
    candidate_id="cand-42",
    topic="VibeWorks CLI ships local agents",
    content_cluster=ContentCluster.VIBE_CODING,
    content_format=ContentFormat.PRACTICAL_GUIDE,
    target_platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
    research_required=False,
    experiment_required=True,
    angle="How it changes the practical dev process",
    hook="VibeWorks CLI ships local agents",
    objective="Teach the task step by step",
    cta="Repeat the steps",
    cta_link="https://example.com/winner",
    tone="teaching and practical",
    structure=PLAN_STRUCTURE,
    language="ru",
    mode="growth",
)

PROVENANCE = SourceProvenance(
    candidate_id="cand-42",
    source_url="https://github.com/vibeworks/cli",
    source_name="GitHub",
    source_type="github",
    discovered_at="2026-09-18T18:00:00+00:00",
    published_at="2026-09-18T12:00:00+00:00",
    verification_status="verified",
    verification_confidence=0.9,
)

ARTIFACT = PackageArtifact(
    artifact_id="art-1",
    kind=ArtifactKind.SOURCE,
    uri="https://github.com/vibeworks/cli",
    title="VibeWorks CLI release notes",
    metadata={"kind": "release"},
)

VARIANT = PlatformVariantRef(
    variant_id="var-1",
    platform=TargetPlatform.TELEGRAM,
    content_ref="ref:telegram:draft-1",
    quality_state=QualityState.NOT_CHECKED,
    publication_state=PublicationState.NOT_READY,
)

ANALYTICS = AnalyticsLink(
    analytics_id="an-1",
    platform=TargetPlatform.TELEGRAM,
    external_post_id="tg-123",
)

PACKAGE = ContentPackageV2(
    package_id="pkg-1",
    candidate_id="cand-42",
    strategy=STRATEGIST_PLAN,
    provenance=PROVENANCE,
    stage=PackageStage.STRATEGY_READY,
    quality_state=QualityState.NOT_CHECKED,
    publication_state=PublicationState.NOT_READY,
    artifacts=(ARTIFACT,),
    platform_variants=(VARIANT,),
    analytics_links=(ANALYTICS,),
    created_at="2026-09-18T18:00:00+00:00",
    updated_at="2026-09-18T18:00:00+00:00",
    legacy_content_id="ci-legacy-1",
)


class TestEnumContracts(unittest.TestCase):
    def test_package_stage_exact_values_and_order(self):
        self.assertEqual(
            [stage.value for stage in PackageStage],
            [
                "strategy_ready",
                "research_pending",
                "research_ready",
                "creation_pending",
                "content_ready",
                "adaptation_pending",
                "variants_ready",
                "qa_pending",
                "approved",
                "publishing",
                "published",
                "analyzed",
                "archived",
                "manual_review",
            ],
        )

    def test_artifact_kind_exact_values(self):
        self.assertEqual(
            [kind.value for kind in ArtifactKind],
            ["research", "experiment", "text", "image", "video", "source"],
        )

    def test_quality_state_exact_values(self):
        self.assertEqual(
            [state.value for state in QualityState],
            ["not_checked", "pending", "approved", "rejected", "manual_review"],
        )

    def test_publication_state_exact_values(self):
        self.assertEqual(
            [state.value for state in PublicationState],
            [
                "not_ready",
                "ready",
                "publishing",
                "partially_published",
                "published",
                "failed",
                "manual_review",
            ],
        )


class TestFrozenDataclasses(unittest.TestCase):
    def test_all_five_are_dataclasses_and_frozen(self):
        for cls in (
            SourceProvenance,
            PackageArtifact,
            PlatformVariantRef,
            AnalyticsLink,
            ContentPackageV2,
        ):
            with self.subTest(cls=cls.__name__):
                self.assertTrue(dataclasses.is_dataclass(cls))
                self.assertIs(cls.__dataclass_params__.frozen, True)


class TestExactFieldOrder(unittest.TestCase):
    def test_source_provenance_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(SourceProvenance)],
            [
                "candidate_id",
                "source_url",
                "source_name",
                "source_type",
                "discovered_at",
                "published_at",
                "verification_status",
                "verification_confidence",
            ],
        )

    def test_package_artifact_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(PackageArtifact)],
            ["artifact_id", "kind", "uri", "title", "metadata"],
        )

    def test_platform_variant_ref_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(PlatformVariantRef)],
            ["variant_id", "platform", "content_ref", "quality_state", "publication_state"],
        )

    def test_analytics_link_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(AnalyticsLink)],
            ["analytics_id", "platform", "external_post_id"],
        )

    def test_content_package_v2_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(ContentPackageV2)],
            [
                "package_id",
                "candidate_id",
                "strategy",
                "provenance",
                "stage",
                "quality_state",
                "publication_state",
                "artifacts",
                "platform_variants",
                "analytics_links",
                "created_at",
                "updated_at",
                "legacy_content_id",
            ],
        )


class TestNoDefaults(unittest.TestCase):
    def test_every_field_has_no_default_and_no_default_factory(self):
        for cls in (
            SourceProvenance,
            PackageArtifact,
            PlatformVariantRef,
            AnalyticsLink,
            ContentPackageV2,
        ):
            for field in dataclasses.fields(cls):
                with self.subTest(cls=cls.__name__, field=field.name):
                    self.assertIs(field.default, dataclasses.MISSING)
                    self.assertIs(field.default_factory, dataclasses.MISSING)


class TestIdentityPreservation(unittest.TestCase):
    def test_package_preserves_nested_objects_by_identity(self):
        artifacts = (ARTIFACT,)
        platform_variants = (VARIANT,)
        analytics_links = (ANALYTICS,)
        package = ContentPackageV2(
            package_id="pkg-1",
            candidate_id="cand-42",
            strategy=STRATEGIST_PLAN,
            provenance=PROVENANCE,
            stage=PackageStage.STRATEGY_READY,
            quality_state=QualityState.NOT_CHECKED,
            publication_state=PublicationState.NOT_READY,
            artifacts=artifacts,
            platform_variants=platform_variants,
            analytics_links=analytics_links,
            created_at="2026-09-18T18:00:00+00:00",
            updated_at="2026-09-18T18:00:00+00:00",
            legacy_content_id="ci-legacy-1",
        )
        self.assertIs(package.strategy, STRATEGIST_PLAN)
        self.assertIs(package.provenance, PROVENANCE)
        self.assertIs(package.artifacts, artifacts)
        self.assertIs(package.platform_variants, platform_variants)
        self.assertIs(package.analytics_links, analytics_links)


class TestValuePreservation(unittest.TestCase):
    def test_representative_values_survive_unchanged(self):
        self.assertEqual(PACKAGE.package_id, "pkg-1")
        self.assertEqual(PACKAGE.candidate_id, "cand-42")
        self.assertEqual(PACKAGE.created_at, "2026-09-18T18:00:00+00:00")
        self.assertEqual(PACKAGE.updated_at, "2026-09-18T18:00:00+00:00")
        self.assertEqual(PACKAGE.legacy_content_id, "ci-legacy-1")
        self.assertIs(PACKAGE.stage, PackageStage.STRATEGY_READY)
        self.assertIs(PACKAGE.quality_state, QualityState.NOT_CHECKED)
        self.assertIs(PACKAGE.publication_state, PublicationState.NOT_READY)

    def test_variant_platform_preserved_exactly(self):
        self.assertIs(VARIANT.platform, TargetPlatform.TELEGRAM)


class TestImmutability(unittest.TestCase):
    def test_source_provenance_assignment_raises(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            PROVENANCE.source_url = "https://example.com/other"

    def test_package_artifact_assignment_raises(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ARTIFACT.title = "other"

    def test_platform_variant_ref_assignment_raises(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            VARIANT.content_ref = "other"

    def test_analytics_link_assignment_raises(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ANALYTICS.external_post_id = "other"

    def test_content_package_v2_assignment_raises(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            PACKAGE.stage = PackageStage.PUBLISHED


class TestContractHasNoMethods(unittest.TestCase):
    def test_no_owned_methods_on_contracts(self):
        for cls in (
            SourceProvenance,
            PackageArtifact,
            PlatformVariantRef,
            AnalyticsLink,
            ContentPackageV2,
        ):
            for name in ("to_dict", "from_dict", "validate", "transition", "can_transition"):
                with self.subTest(cls=cls.__name__, name=name):
                    self.assertNotIn(name, cls.__dict__)


class TestNoLegacyTypeAliasing(unittest.TestCase):
    def test_content_package_v2_is_not_legacy_content_package(self):
        from src.domain.strategy import ContentPackage as LegacyContentPackage

        self.assertIsNot(ContentPackageV2, LegacyContentPackage)

    def test_platform_variant_ref_is_not_legacy_platform_variant(self):
        from src.domain.strategy import PlatformVariant as LegacyPlatformVariant

        self.assertIsNot(PlatformVariantRef, LegacyPlatformVariant)


def _module_source() -> str:
    return MODULE_PATH.read_text(encoding="utf-8")


def _module_tree() -> ast.Module:
    return ast.parse(_module_source())


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


class TestNoSideEffectCoupling(unittest.TestCase):
    def _assert_absent(self, tokens):
        tree = _module_tree()
        ids = _module_ids(tree)
        leaks = sorted(token for token in tokens if token in ids)
        self.assertEqual(leaks, [])

    def test_no_forbidden_imports_or_references(self):
        self._assert_absent(
            [
                "StateService",
                "sqlite3",
                "Config",
                "datetime",
                "time",
                "os",
                "pathlib",
                "requests",
                "httpx",
                "publisher",
                "copywriter",
                "editor",
                "designer",
                "telegram",
                "x_client",
                "vk_client",
                "pinterest_client",
            ]
        )

    def test_no_open_or_print_calls(self):
        tree = _module_tree()
        call_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertEqual(call_names & {"open", "print"}, set())


class TestNoBuildersSerializationValidation(unittest.TestCase):
    def test_zero_module_level_function_definitions(self):
        tree = _module_tree()
        functions = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(functions, [])

    def test_module_contains_only_imports_enums_dataclasses_and_all(self):
        tree = _module_tree()
        for node in tree.body:
            with self.subTest(node=type(node).__name__):
                self.assertIsInstance(
                    node,
                    (
                        ast.Import,
                        ast.ImportFrom,
                        ast.ClassDef,
                        ast.Assign,
                        ast.AnnAssign,
                        ast.Expr,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
