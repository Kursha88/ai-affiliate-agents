"""Step 16B unit tests: deterministic ContentPackageV2 builder boundary.

Covers the success path (provenance snapshot, initial states, empty
collections, caller-supplied identity/time, StrategistPlan identity),
upstream immutability, the exact nine ordered boundary validation errors,
the absence of hidden validation policy, and structural AST guarantees for
the builder module (no side effects, no orchestration, no generation).
"""

import ast
import unittest
from pathlib import Path

from src.content.content_package_builder import build_content_package
from src.domain.content_package import (
    ContentPackageV2,
    PackageStage,
    PublicationState,
    QualityState,
    SourceProvenance,
)
from src.domain.strategy import (
    CandidateScore,
    CandidateStage,
    ContentCandidate,
    ContentCluster,
    ContentFormat,
    DiscoveryCandidate,
    SourceType,
    StrategicSelection,
    TargetPlatform,
    VerificationResult,
    VerificationStatus,
)
from src.domain.strategist import StrategistPlan

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "content"
    / "content_package_builder.py"
)

CANDIDATE_ID = "cand-123"
PLATFORMS = (
    TargetPlatform.TELEGRAM,
    TargetPlatform.X,
    TargetPlatform.LINKEDIN,
    TargetPlatform.PINTEREST,
)
STRUCTURE = ("problem", "tool", "key_features", "use_case", "cta")
PACKAGE_ID = "pkg-001"
CREATED_AT = "2026-09-19T11:00:00+00:00"
UPDATED_AT = "2026-09-19T11:00:00+00:00"


# ──────────────────────────────────────────────────────────────────────
# Real domain fixtures
# ──────────────────────────────────────────────────────────────────────

def _discovery() -> DiscoveryCandidate:
    return DiscoveryCandidate(
        candidate_id=CANDIDATE_ID,
        title="Example AI tool",
        source_type=SourceType.GITHUB,
        source_url="https://github.com/example/tool",
        discovered_at="2026-09-19T10:00:00+00:00",
        content_cluster=ContentCluster.AI_TOOLS,
        source_name="github",
        published_at="2026-09-19T09:00:00+00:00",
    )


def _verification() -> VerificationResult:
    return VerificationResult(
        verification_status=VerificationStatus.VERIFIED,
        primary_source_found=True,
        primary_source_url="https://github.com/example/tool",
        confidence=0.91,
        notes="verified",
    )


def _score() -> CandidateScore:
    return CandidateScore(
        novelty=0.8,
        practical_utility=0.9,
        free_availability=1.0,
        audience_interest=0.7,
        viral_potential=0.6,
        credibility=0.85,
    )


def _selection(**overrides) -> StrategicSelection:
    defaults = dict(
        selected=True,
        selection_reason="best candidate",
        recommended_format=ContentFormat.TOOL_DISCOVERY,
        target_platforms=PLATFORMS,
        research_required=False,
        experiment_required=False,
    )
    defaults.update(overrides)
    return StrategicSelection(**defaults)


_NO_SELECTION = object()  # sentinel: "no selection kwarg supplied"


def _make_candidate(*, stage=CandidateStage.SELECTED, selection=_NO_SELECTION) -> ContentCandidate:
    return ContentCandidate(
        candidate=_discovery(),
        verification=_verification(),
        score=_score(),
        selection=_selection() if selection is _NO_SELECTION else selection,
        stage=stage,
        content_id=None,
    )


def _make_plan(**overrides) -> StrategistPlan:
    defaults = dict(
        candidate_id=CANDIDATE_ID,
        topic="Example AI tool",
        content_cluster=ContentCluster.AI_TOOLS,
        content_format=ContentFormat.TOOL_DISCOVERY,
        target_platforms=PLATFORMS,
        research_required=False,
        experiment_required=False,
        angle="Как инструмент решает конкретную практическую проблему",
        hook="Example AI tool",
        objective="Показать, зачем нужен инструмент и где он полезен",
        cta="Изучить инструмент",
        cta_link="https://github.com/example/tool",
        tone="практичный и конкретный",
        structure=STRUCTURE,
        language="ru",
        mode="growth",
    )
    defaults.update(overrides)
    return StrategistPlan(**defaults)


def _build(content_candidate=None, strategist_plan=None, **kwargs):
    if content_candidate is None:
        content_candidate = _make_candidate()
    if strategist_plan is None:
        strategist_plan = _make_plan()
    params = dict(
        package_id=PACKAGE_ID,
        created_at=CREATED_AT,
        updated_at=UPDATED_AT,
    )
    params.update(kwargs)
    return build_content_package(content_candidate, strategist_plan, **params)


# ──────────────────────────────────────────────────────────────────────
# Behavioral tests
# ──────────────────────────────────────────────────────────────────────

class TestSuccessPath(unittest.TestCase):
    def setUp(self):
        self.package = _build()

    def test_returns_content_package_v2(self):
        self.assertIsInstance(self.package, ContentPackageV2)

    def test_package_id_preserved_exactly(self):
        self.assertEqual(self.package.package_id, PACKAGE_ID)

    def test_candidate_id_comes_from_content_candidate(self):
        self.assertEqual(self.package.candidate_id, CANDIDATE_ID)

    def test_strategy_is_exact_strategist_plan_object(self):
        plan = _make_plan()
        package = _build(strategist_plan=plan)
        self.assertIs(package.strategy, plan)

    def test_provenance_is_source_provenance(self):
        self.assertIsInstance(self.package.provenance, SourceProvenance)

    def test_provenance_candidate_id_exact(self):
        self.assertEqual(self.package.provenance.candidate_id, CANDIDATE_ID)

    def test_provenance_source_url_exact(self):
        self.assertEqual(
            self.package.provenance.source_url, "https://github.com/example/tool"
        )

    def test_provenance_source_name_exact(self):
        self.assertEqual(self.package.provenance.source_name, "github")

    def test_provenance_source_type_is_github_value(self):
        self.assertEqual(self.package.provenance.source_type, SourceType.GITHUB.value)

    def test_provenance_discovered_at_exact(self):
        self.assertEqual(
            self.package.provenance.discovered_at, "2026-09-19T10:00:00+00:00"
        )

    def test_provenance_published_at_exact(self):
        self.assertEqual(
            self.package.provenance.published_at, "2026-09-19T09:00:00+00:00"
        )

    def test_provenance_verification_status_is_verified_value(self):
        self.assertEqual(
            self.package.provenance.verification_status,
            VerificationStatus.VERIFIED.value,
        )

    def test_provenance_verification_confidence_exact(self):
        self.assertEqual(self.package.provenance.verification_confidence, 0.91)

    def test_stage_is_strategy_ready(self):
        self.assertIs(self.package.stage, PackageStage.STRATEGY_READY)

    def test_quality_state_is_not_checked(self):
        self.assertIs(self.package.quality_state, QualityState.NOT_CHECKED)

    def test_publication_state_is_not_ready(self):
        self.assertIs(self.package.publication_state, PublicationState.NOT_READY)

    def test_artifacts_empty_tuple(self):
        self.assertEqual(self.package.artifacts, ())

    def test_platform_variants_empty_tuple(self):
        self.assertEqual(self.package.platform_variants, ())

    def test_analytics_links_empty_tuple(self):
        self.assertEqual(self.package.analytics_links, ())

    def test_created_at_preserved_exactly(self):
        self.assertEqual(self.package.created_at, CREATED_AT)

    def test_updated_at_preserved_exactly(self):
        self.assertEqual(self.package.updated_at, UPDATED_AT)

    def test_legacy_content_id_preserves_non_none_value(self):
        package = _build(legacy_content_id="ci-legacy-9")
        self.assertEqual(package.legacy_content_id, "ci-legacy-9")

    def test_legacy_content_id_preserves_none(self):
        self.assertIsNone(self.package.legacy_content_id)


class TestNoPlatformPlaceholders(unittest.TestCase):
    def test_four_target_platforms_yield_zero_variants(self):
        plan = _make_plan()
        # Precondition: the strategist plan really carries 4 platforms.
        self.assertEqual(len(plan.target_platforms), 4)
        package = _build(strategist_plan=plan)
        self.assertEqual(package.platform_variants, ())
        self.assertEqual(len(package.platform_variants), 0)


class TestInputImmutability(unittest.TestCase):
    def test_upstream_objects_unchanged_after_build(self):
        candidate = _make_candidate()
        plan = _make_plan()
        discovery = candidate.candidate
        verification = candidate.verification
        selection = candidate.selection
        plan_platforms = plan.target_platforms
        plan_structure = plan.structure

        package = _build(content_candidate=candidate, strategist_plan=plan)

        # Identity preservation of every upstream reference.
        self.assertIs(package.strategy, plan)
        self.assertIs(candidate.candidate, discovery)
        self.assertIs(candidate.verification, verification)
        self.assertIs(candidate.selection, selection)
        self.assertIs(plan.target_platforms, plan_platforms)
        self.assertIs(plan.structure, plan_structure)

        # Representative values unchanged (no mutation, no coercion).
        self.assertEqual(candidate.stage, CandidateStage.SELECTED)
        self.assertIsNone(candidate.content_id)
        self.assertIs(selection.selected, True)
        self.assertEqual(selection.target_platforms, PLATFORMS)
        self.assertEqual(selection.recommended_format, ContentFormat.TOOL_DISCOVERY)
        self.assertEqual(plan.candidate_id, CANDIDATE_ID)
        self.assertEqual(plan.content_cluster, ContentCluster.AI_TOOLS)
        self.assertEqual(verification.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(verification.confidence, 0.91)
        self.assertEqual(discovery.source_url, "https://github.com/example/tool")


class TestValidationExactMessages(unittest.TestCase):
    def test_wrong_stage_raises_exact_error(self):
        candidate = _make_candidate(stage=CandidateStage.SCORED)
        with self.assertRaises(ValueError) as ctx:
            _build(content_candidate=candidate)
        self.assertEqual(str(ctx.exception), "content candidate is not at selected stage")

    def test_missing_selection_raises_exact_error(self):
        candidate = _make_candidate(selection=None)
        self.assertEqual(candidate.stage, CandidateStage.SELECTED)
        with self.assertRaises(ValueError) as ctx:
            _build(content_candidate=candidate)
        self.assertEqual(
            str(ctx.exception), "content candidate missing strategic selection"
        )

    def test_not_selected_selection_raises_exact_error(self):
        candidate = _make_candidate(selection=_selection(selected=False))
        with self.assertRaises(ValueError) as ctx:
            _build(content_candidate=candidate)
        self.assertEqual(str(ctx.exception), "strategic selection is not selected")

    def test_candidate_id_mismatch_raises_exact_error(self):
        with self.assertRaises(ValueError) as ctx:
            _build(strategist_plan=_make_plan(candidate_id="cand-999"))
        self.assertEqual(
            str(ctx.exception),
            "candidate_id mismatch between candidate and strategist plan",
        )

    def test_content_cluster_mismatch_raises_exact_error(self):
        with self.assertRaises(ValueError) as ctx:
            _build(strategist_plan=_make_plan(content_cluster=ContentCluster.AI_AGENTS))
        self.assertEqual(
            str(ctx.exception),
            "content_cluster mismatch between candidate and strategist plan",
        )

    def test_content_format_mismatch_raises_exact_error(self):
        with self.assertRaises(ValueError) as ctx:
            _build(
                strategist_plan=_make_plan(content_format=ContentFormat.PRACTICAL_GUIDE)
            )
        self.assertEqual(
            str(ctx.exception),
            "content_format mismatch between selection and strategist plan",
        )

    def test_target_platforms_mismatch_raises_exact_error(self):
        with self.assertRaises(ValueError) as ctx:
            _build(strategist_plan=_make_plan(target_platforms=(TargetPlatform.X,)))
        self.assertEqual(
            str(ctx.exception),
            "target_platforms mismatch between selection and strategist plan",
        )

    def test_research_required_mismatch_raises_exact_error(self):
        with self.assertRaises(ValueError) as ctx:
            _build(strategist_plan=_make_plan(research_required=True))
        self.assertEqual(
            str(ctx.exception),
            "research_required mismatch between selection and strategist plan",
        )

    def test_experiment_required_mismatch_raises_exact_error(self):
        with self.assertRaises(ValueError) as ctx:
            _build(strategist_plan=_make_plan(experiment_required=True))
        self.assertEqual(
            str(ctx.exception),
            "experiment_required mismatch between selection and strategist plan",
        )


class TestValidationOrder(unittest.TestCase):
    def test_stage_error_wins_over_selection_and_plan_errors(self):
        candidate = _make_candidate(stage=CandidateStage.SCORED, selection=None)
        plan = _make_plan(candidate_id="cand-999")
        with self.assertRaises(ValueError) as ctx:
            _build(content_candidate=candidate, strategist_plan=plan)
        self.assertEqual(str(ctx.exception), "content candidate is not at selected stage")

    def test_selection_error_wins_over_plan_errors(self):
        candidate = _make_candidate(selection=None)
        plan = _make_plan(candidate_id="cand-999")
        self.assertEqual(candidate.stage, CandidateStage.SELECTED)
        with self.assertRaises(ValueError) as ctx:
            _build(content_candidate=candidate, strategist_plan=plan)
        self.assertEqual(
            str(ctx.exception), "content candidate missing strategic selection"
        )

    def test_selected_flag_error_wins_over_plan_errors(self):
        candidate = _make_candidate(selection=_selection(selected=False))
        plan = _make_plan(candidate_id="cand-999")
        with self.assertRaises(ValueError) as ctx:
            _build(content_candidate=candidate, strategist_plan=plan)
        self.assertEqual(str(ctx.exception), "strategic selection is not selected")


class TestNoExtraValidation(unittest.TestCase):
    def test_empty_package_id_accepted_and_preserved(self):
        package = _build(package_id="")
        self.assertEqual(package.package_id, "")

    def test_non_timestamp_created_at_accepted_and_preserved(self):
        package = _build(created_at="not-a-timestamp")
        self.assertEqual(package.created_at, "not-a-timestamp")

    def test_empty_updated_at_accepted_and_preserved(self):
        package = _build(updated_at="")
        self.assertEqual(package.updated_at, "")


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees for the builder module
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


def _calls_by_name(tree: ast.Module, name: str):
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


class TestBuilderStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _module_tree()
        cls.ids = _module_ids(cls.tree)

    def _package_call_keywords(self):
        calls = _calls_by_name(self.tree, "ContentPackageV2")
        self.assertEqual(len(calls), 1)
        return {kw.arg: kw.value for kw in calls[0].keywords}

    def _assert_attribute_keyword(self, keywords, arg, owner, member):
        value = keywords[arg]
        self.assertIsInstance(value, ast.Attribute)
        self.assertEqual(value.attr, member)
        self.assertIsInstance(value.value, ast.Name)
        self.assertEqual(value.value.id, owner)

    def test_exactly_one_module_level_function(self):
        functions = [
            node for node in self.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual([f.name for f in functions], ["build_content_package"])

    def test_all_is_exactly_builder_function(self):
        assigns = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
            )
        ]
        self.assertEqual(len(assigns), 1)
        values = [elt.value for elt in assigns[0].value.elts]
        self.assertEqual(values, ["build_content_package"])

    def test_no_forbidden_imports_or_references(self):
        forbidden = {
            # Time / identity generation.
            "datetime", "time", "uuid", "hashlib", "random",
            # Persistence / config / DB.
            "StateService", "sqlite3", "Config",
            # Filesystem / network.
            "os", "pathlib", "requests", "httpx",
            # Social / publishing integrations.
            "publisher", "copywriter", "editor", "designer",
            "telegram", "x_client", "vk_client", "pinterest_client",
            # Orchestration entry points.
            "run_strategist", "build_strategist_input", "build_strategist_plan",
            "build_strategist_enrichment", "run_select_stage", "run_live_research",
            "content_candidate_to_news_item", "strategist_plan_to_legacy_plan",
            # Rebuild / mutation helpers.
            "replace", "deepcopy",
        }
        leaks = sorted(token for token in forbidden if token in self.ids)
        self.assertEqual(leaks, [])

    def test_no_open_or_print_calls(self):
        for name in ("open", "print"):
            self.assertEqual(_calls_by_name(self.tree, name), [])

    def test_exactly_one_content_package_v2_construction(self):
        self.assertEqual(len(_calls_by_name(self.tree, "ContentPackageV2")), 1)

    def test_exactly_one_source_provenance_construction(self):
        self.assertEqual(len(_calls_by_name(self.tree, "SourceProvenance")), 1)

    def test_strategy_keyword_receives_strategist_plan_name(self):
        keywords = self._package_call_keywords()
        value = keywords["strategy"]
        self.assertIsInstance(value, ast.Name)
        self.assertEqual(value.id, "strategist_plan")

    def test_stage_keyword_uses_strategy_ready(self):
        keywords = self._package_call_keywords()
        self._assert_attribute_keyword(keywords, "stage", "PackageStage", "STRATEGY_READY")

    def test_quality_state_keyword_uses_not_checked(self):
        keywords = self._package_call_keywords()
        self._assert_attribute_keyword(
            keywords, "quality_state", "QualityState", "NOT_CHECKED"
        )

    def test_publication_state_keyword_uses_not_ready(self):
        keywords = self._package_call_keywords()
        self._assert_attribute_keyword(
            keywords, "publication_state", "PublicationState", "NOT_READY"
        )

    def test_collection_keywords_are_empty_tuple_literals(self):
        keywords = self._package_call_keywords()
        for arg in ("artifacts", "platform_variants", "analytics_links"):
            with self.subTest(arg=arg):
                value = keywords[arg]
                self.assertIsInstance(value, ast.Tuple)
                self.assertEqual(value.elts, [])

    def test_no_loops_or_comprehensions(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, (ast.For, ast.AsyncFor))
            self.assertNotIsInstance(
                node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
            )


if __name__ == "__main__":
    unittest.main()
