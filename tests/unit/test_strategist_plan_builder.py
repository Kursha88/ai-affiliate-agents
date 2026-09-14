"""Step 15C — deterministic StrategistPlan assembler with lossless SELECT
preservation.

Tests use REAL domain types and the smallest valid selected candidate
fixture (VerificationResult defaults and score=None are fine: this
assembler must ignore them).
"""

import ast
import dataclasses
import inspect
import unittest
from pathlib import Path

from src.domain.strategy import (
    CandidateStage,
    ContentCandidate,
    ContentCluster,
    ContentFormat,
    DiscoveryCandidate,
    SourceType,
    StrategicSelection,
    TargetPlatform,
    VerificationResult,
)
from src.domain.strategist import StrategistInput, StrategistPlan
from src.strategy.strategist_plan import build_strategist_plan

MODULE_PATH = Path("src/strategy/strategist_plan.py")

_ENRICHMENT = {
    "angle": "hands-on angle",
    "hook": "Your IDE just got an agent",
    "objective": "teach the reader to try it today",
    "cta": "Try it yourself",
    "cta_link": "https://example.com/repo",
    "tone": "practical",
    "structure": ("hook", "body", "cta"),
    "language": "ru",
    "mode": "growth",
}

_UNSET = object()


def make_selection(
    *,
    selected=True,
    format=ContentFormat.PRACTICAL_GUIDE,
    platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
    research=False,
    experiment=False,
) -> StrategicSelection:
    return StrategicSelection(
        selected=selected,
        selection_reason="selected_test",
        recommended_format=format,
        target_platforms=platforms,
        research_required=research,
        experiment_required=experiment,
    )


def make_input(
    *,
    title="Open-source coding agent",
    candidate_id="cand-1",
    selection=_UNSET,
    cluster=ContentCluster.VIBE_CODING,
) -> StrategistInput:
    if selection is _UNSET:
        selection = make_selection()
    discovery = DiscoveryCandidate(
        candidate_id=candidate_id,
        title=title,
        source_type=SourceType.GITHUB,
        source_url="https://github.com/owner/repo",
        discovered_at="2026-09-14T00:00:00+00:00",
        content_cluster=cluster,
    )
    candidate = ContentCandidate(
        candidate=discovery,
        verification=VerificationResult(),
        score=None,
        selection=selection,
        stage=CandidateStage.SELECTED,
    )
    return StrategistInput(content_candidate=candidate)


def build_plan(strategist_input, **overrides) -> StrategistPlan:
    values = dict(_ENRICHMENT)
    values.update(overrides)
    return build_strategist_plan(strategist_input, **values)


class TestBasicResult(unittest.TestCase):
    """Tests 1-3."""

    def setUp(self):
        self.s_input = make_input()

    # 1
    def test_returns_real_strategist_plan(self):
        self.assertIsInstance(build_plan(self.s_input), StrategistPlan)

    # 2
    def test_candidate_id_copied_exactly(self):
        plan = build_plan(self.s_input)
        self.assertEqual(plan.candidate_id, "cand-1")

    # 3
    def test_topic_copied_exactly_from_title(self):
        title = "continuedev/continue: open-source coding agent"
        s_input = make_input(title=title)
        plan = build_plan(s_input)
        self.assertEqual(plan.topic, title)


class TestSelectPreservation(unittest.TestCase):
    """Tests 4-17: lossless SELECT-owned decision preservation."""

    def test_cluster_preserved_exactly(self):
        # 4 + 14: every real cluster passes unchanged.
        for cluster in ContentCluster:
            with self.subTest(cluster=cluster):
                plan = build_plan(make_input(cluster=cluster))
                self.assertIs(plan.content_cluster, cluster)

    def test_format_preserved_exactly(self):
        # 5 + 15: every real format passes unchanged.
        for fmt in ContentFormat:
            with self.subTest(format=fmt):
                plan = build_plan(
                    make_input(selection=make_selection(format=fmt))
                )
                self.assertIs(plan.content_format, fmt)

    def test_platforms_preserved_by_value_order_and_identity(self):
        # 6, 7, 8 + 16, 17: value, identity and order — one and many.
        cases = (
            (TargetPlatform.TELEGRAM,),
            (
                TargetPlatform.PINTEREST,   # deliberately non-declaration order
                TargetPlatform.X,
                TargetPlatform.YOUTUBE_SHORTS,
            ),
        )
        for platforms in cases:
            with self.subTest(platforms=platforms):
                selection = make_selection(platforms=platforms)
                plan = build_plan(make_input(selection=selection))
                self.assertEqual(plan.target_platforms, platforms)
                self.assertIs(plan.target_platforms, platforms)
                self.assertEqual(
                    plan.target_platforms,
                    tuple(platforms),  # same values in the same order
                )

    # 9, 13
    def test_research_required_combinations(self):
        for research in (False, True):
            with self.subTest(research=research):
                plan = build_plan(
                    make_input(selection=make_selection(research=research))
                )
                self.assertIs(plan.research_required, research)

    # 10
    def test_research_required_true_preserved(self):
        plan = build_plan(make_input(selection=make_selection(research=True)))
        self.assertIs(plan.research_required, True)

    # 11, 13
    def test_experiment_required_combinations(self):
        for experiment in (False, True):
            with self.subTest(experiment=experiment):
                plan = build_plan(
                    make_input(selection=make_selection(experiment=experiment))
                )
                self.assertIs(plan.experiment_required, experiment)

    # 12
    def test_experiment_required_true_preserved(self):
        plan = build_plan(
            make_input(selection=make_selection(experiment=True))
        )
        self.assertIs(plan.experiment_required, True)

    # 13
    def test_all_four_boolean_combinations_preserved(self):
        for research in (False, True):
            for experiment in (False, True):
                with self.subTest(research=research, experiment=experiment):
                    plan = build_plan(
                        make_input(
                            selection=make_selection(
                                research=research, experiment=experiment
                            )
                        )
                    )
                    self.assertIs(plan.research_required, research)
                    self.assertIs(plan.experiment_required, experiment)


class TestExplicitEnrichment(unittest.TestCase):
    """Tests 18-30."""

    def test_enrichment_strings_preserved_exactly(self):
        # 18-23, 27, 28: every scalar enrichment field.
        s_input = make_input()
        plan = build_plan(s_input)
        for name in (
            "angle",
            "hook",
            "objective",
            "cta",
            "cta_link",
            "tone",
            "language",
            "mode",
        ):
            with self.subTest(field=name):
                self.assertEqual(getattr(plan, name), _ENRICHMENT[name])

    # 24, 25, 26
    def test_structure_preserved_by_value_identity_and_order(self):
        structure = ("z-section", "a-section", "m-section")
        plan = build_plan(make_input(), structure=structure)
        self.assertEqual(plan.structure, structure)
        self.assertIs(plan.structure, structure)
        self.assertEqual(plan.structure, ("z-section", "a-section", "m-section"))

    # 29
    def test_unicode_emoji_preserved_without_normalization(self):
        weird = {
            "angle": "угол  <>&✨",
            "hook": "хук 🚀 /:@#",
            "objective": "цель — 100%",
            "cta": "CTA→🚀",
            "cta_link": "https://example.com/cta?x=1#frag",
            "tone": "тон✌",
            "structure": ("секция 1 ", " секция2", "СЕКЦИЯ 3"),
            "language": "ru-RU",
            "mode": "mode·2026",
        }
        plan = build_plan(make_input(), **weird)
        for name, value in weird.items():
            with self.subTest(field=name):
                self.assertEqual(getattr(plan, name), value)

    # 30
    def test_empty_enrichment_strings_preserved_exactly(self):
        plan = build_plan(
            make_input(),
            angle="",
            hook="",
            objective="",
            cta="",
            cta_link="",
            tone="",
            structure=(),
            language="",
            mode="",
        )
        for name in (
            "angle",
            "hook",
            "objective",
            "cta",
            "cta_link",
            "tone",
            "structure",
            "language",
            "mode",
        ):
            with self.subTest(field=name):
                self.assertEqual(getattr(plan, name), "" if name != "structure" else ())


class TestRequiredArguments(unittest.TestCase):
    """Tests 31-39 via inspect.signature (spec-preferred)."""

    # 31-39
    def test_all_enrichment_arguments_required(self):
        sig = inspect.signature(build_strategist_plan)
        self.assertIn("strategist_input", sig.parameters)
        self.assertEqual(
            sig.parameters["strategist_input"].kind,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        required = (
            "angle",
            "hook",
            "objective",
            "cta",
            "cta_link",
            "tone",
            "structure",
            "language",
            "mode",
        )
        for name in required:
            param = sig.parameters.get(name)
            with self.subTest(param=name):
                self.assertIsNotNone(param)
                self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertEqual(param.default, inspect.Parameter.empty)


class TestDefensiveMalformedInput(unittest.TestCase):
    """Tests 40-44: exact messages and validation order."""

    # 40
    def test_missing_selection_raises_exact_error(self):
        # ContentCandidate legally allows selection=None; build that state
        # directly and wrap it in a manually-created StrategistInput.
        discovery = DiscoveryCandidate(
            candidate_id="cand-1",
            title="Test candidate",
            source_type=SourceType.GITHUB,
            source_url="https://github.com/owner/repo",
            discovered_at="2026-09-14T00:00:00+00:00",
            content_cluster=ContentCluster.VIBE_CODING,
        )
        orphan = ContentCandidate(
            candidate=discovery,
            verification=VerificationResult(),
            score=None,
            selection=None,
            stage=CandidateStage.SELECTED,
        )
        with self.assertRaises(ValueError) as ctx:
            build_plan(StrategistInput(content_candidate=orphan))
        self.assertEqual(
            str(ctx.exception),
            "strategist input missing strategic selection",
        )

    # 41
    def test_missing_format_raises_exact_error(self):
        s_input = make_input(selection=make_selection(format=None))
        with self.assertRaises(ValueError) as ctx:
            build_plan(s_input)
        self.assertEqual(
            str(ctx.exception),
            "strategist input missing recommended format",
        )

    # 42
    def test_missing_cluster_raises_exact_error(self):
        s_input = make_input(cluster=None)
        with self.assertRaises(ValueError) as ctx:
            build_plan(s_input)
        self.assertEqual(
            str(ctx.exception),
            "strategist input missing content cluster",
        )

    # 43
    def test_missing_selection_beats_missing_cluster(self):
        discovery = DiscoveryCandidate(
            candidate_id="cand-1",
            title="Test candidate",
            source_type=SourceType.GITHUB,
            source_url="https://github.com/owner/repo",
            discovered_at="2026-09-14T00:00:00+00:00",
            content_cluster=None,  # also invalid — but selection error wins
        )
        orphan = ContentCandidate(
            candidate=discovery,
            verification=VerificationResult(),
            score=None,
            selection=None,
            stage=CandidateStage.SELECTED,
        )
        with self.assertRaises(ValueError) as ctx:
            build_plan(StrategistInput(content_candidate=orphan))
        self.assertEqual(
            str(ctx.exception),
            "strategist input missing strategic selection",
        )

    # 44
    def test_missing_format_beats_missing_cluster(self):
        s_input = make_input(
            selection=make_selection(format=None), cluster=None
        )
        with self.assertRaises(ValueError) as ctx:
            build_plan(s_input)
        self.assertEqual(
            str(ctx.exception),
            "strategist input missing recommended format",
        )


class TestPurityNoRecomputation(unittest.TestCase):
    """Tests 45-55."""

    # 45
    def test_selection_reason_ignored(self):
        for reason in ("", "below_selection_threshold", "anything"):
            with self.subTest(reason=reason):
                selection = StrategicSelection(
                    selected=True,
                    selection_reason=reason,
                    recommended_format=ContentFormat.WORKFLOW,
                    target_platforms=(TargetPlatform.X,),
                )
                plan = build_plan(make_input(selection=selection))
                self.assertEqual(plan.candidate_id, "cand-1")

    # 46
    def test_score_ignored(self):
        plan = build_plan(make_input())  # score=None fixture
        self.assertEqual(plan.candidate_id, "cand-1")

    # 47
    def test_verification_ignored(self):
        plan = build_plan(make_input())  # default VerificationResult fixture
        self.assertEqual(plan.candidate_id, "cand-1")

    # 48
    def test_content_id_ignored(self):
        discovery = DiscoveryCandidate(
            candidate_id="cand-1",
            title="T",
            source_type=SourceType.GITHUB,
            source_url="https://github.com/owner/repo",
            discovered_at="2026-09-14T00:00:00+00:00",
            content_cluster=ContentCluster.VIBE_CODING,
        )
        candidate = ContentCandidate(
            candidate=discovery,
            verification=VerificationResult(),
            score=None,
            selection=make_selection(),
            stage=CandidateStage.SELECTED,
            content_id="content-42",
        )
        plan = build_plan(StrategistInput(content_candidate=candidate))
        self.assertEqual(plan.candidate_id, "cand-1")

    # 49
    def test_stage_not_read_or_revalidated(self):
        # Manually-created input at a non-SELECTED stage must still assemble
        # (stage is a boundary responsibility, not the assembler's).
        discovery = DiscoveryCandidate(
            candidate_id="cand-1",
            title="T",
            source_type=SourceType.GITHUB,
            source_url="https://github.com/owner/repo",
            discovered_at="2026-09-14T00:00:00+00:00",
            content_cluster=ContentCluster.VIBE_CODING,
        )
        candidate = ContentCandidate(
            candidate=discovery,
            verification=VerificationResult(),
            score=None,
            selection=make_selection(),
            stage=CandidateStage.SCORED,  # not SELECTED
        )
        plan = build_plan(StrategistInput(content_candidate=candidate))
        self.assertEqual(plan.candidate_id, "cand-1")

    # 50
    def test_selected_flag_not_read_or_revalidated(self):
        selection = StrategicSelection(
            selected=False,  # not selected
            selection_reason="",
            recommended_format=ContentFormat.WORKFLOW,
            target_platforms=(TargetPlatform.X,),
        )
        plan = build_plan(make_input(selection=selection))
        self.assertEqual(plan.candidate_id, "cand-1")

    # 51
    def test_empty_platforms_preserved_not_revalidated(self):
        selection = make_selection(platforms=())
        plan = build_plan(make_input(selection=selection))
        self.assertEqual(plan.target_platforms, ())
        self.assertIs(plan.target_platforms, selection.target_platforms)

    # 52-54
    def test_no_mutation_of_inputs(self):
        selection = make_selection()
        discovery = DiscoveryCandidate(
            candidate_id="cand-1",
            title="Test candidate",
            source_type=SourceType.GITHUB,
            source_url="https://github.com/owner/repo",
            discovered_at="2026-09-14T00:00:00+00:00",
            content_cluster=ContentCluster.VIBE_CODING,
        )
        candidate = ContentCandidate(
            candidate=discovery,
            verification=VerificationResult(),
            score=None,
            selection=selection,
            stage=CandidateStage.SELECTED,
        )
        s_input = StrategistInput(content_candidate=candidate)
        platforms_before = selection.target_platforms

        plan = build_plan(s_input)

        # Frozen dataclasses: same objects, equal values, untouched.
        self.assertIs(s_input.content_candidate, candidate)
        self.assertIs(s_input.content_candidate.selection, selection)
        self.assertIs(s_input.content_candidate.candidate, discovery)
        self.assertIs(plan.target_platforms, platforms_before)
        self.assertEqual(plan.content_cluster, discovery.content_cluster)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            candidate.stage = CandidateStage.DISCOVERED
        with self.assertRaises(dataclasses.FrozenInstanceError):
            selection.selected = False

    # 55
    def test_deterministic_equal_plans(self):
        s_input = make_input()
        first = build_plan(s_input)
        second = build_plan(s_input)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)


class TestStructuralBoundaries(unittest.TestCase):
    """Tests 56-70: AST/introspection structural guarantees."""

    @classmethod
    def setUpClass(cls):
        cls.source = MODULE_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.func = next(
            node
            for node in ast.walk(cls.tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "build_strategist_plan"
        )
        # Docstring-stripped module source for token scans.
        stripped = ast.parse(cls.source)
        for node in ast.walk(stripped):
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    node.body = body[1:]
        cls.code_only = ast.unparse(stripped)

    def _modules(self):
        modules = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name)
        return modules

    # 56
    def test_all_exports_exact(self):
        import src.strategy.strategist_plan as module

        self.assertEqual(list(module.__all__), ["build_strategist_plan"])

    # 57
    def test_exactly_one_public_function(self):
        top_level = [
            node.name
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef)
        ]
        self.assertEqual(top_level, ["build_strategist_plan"])

    # 58
    def test_strategist_plan_constructed_exactly_once(self):
        constructions = [
            node
            for node in ast.walk(self.func)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "StrategistPlan"
        ]
        self.assertEqual(len(constructions), 1)

    # 59
    def test_no_build_strategist_input_import_or_call(self):
        self.assertNotIn("build_strategist_input", self.code_only)

    # 60
    def test_no_format_platform_default_constants(self):
        self.assertNotIn("ContentFormat.", self.code_only)
        self.assertNotIn("TargetPlatform.", self.code_only)

    # 61
    def test_no_utility_imports(self):
        modules = self._modules()
        for banned in ("datetime", "random", "os", "pathlib", "yaml", "requests"):
            self.assertNotIn(banned, modules)

    # 62
    def test_no_config_main_agents_imports(self):
        self.assertEqual(
            self._modules() & {"src.main", "src.agents", "src.core.config"},
            set(),
        )

    # 63
    def test_no_validators_state_research_imports(self):
        self.assertEqual(
            self._modules()
            & {"src.utils.validators", "src.state", "src.research"},
            set(),
        )
        self.assertNotIn("StateService", self.code_only)

    # 64
    def test_no_try_except(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.Try)

    # 65
    def test_no_dict_plan_construction(self):
        # No dict literal and no dict(...) call anywhere in the function.
        for node in ast.walk(self.func):
            self.assertNotIsInstance(node, ast.Dict)
            self.assertFalse(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "dict"
            )

    # 66
    def test_no_legacy_references(self):
        for banned in ("news_item", "product", "affiliate", "topic_history"):
            self.assertNotIn(banned, self.code_only)

    # 67
    def test_no_mutation_assignments(self):
        for node in ast.walk(self.func):
            if isinstance(node, ast.Attribute):
                self.assertNotIsInstance(node.ctx, ast.Store)

    # 68
    def test_no_transform_calls(self):
        banned_calls = {"strip", "lower", "upper", "sort", "sorted", "tuple", "list", "set"}
        for node in ast.walk(self.func):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    self.assertNotIn(func.attr, banned_calls)
                elif isinstance(func, ast.Name):
                    self.assertNotIn(func.id, banned_calls)

    # 69
    def test_selection_reads_only_allowed_fields(self):
        allowed = {"recommended_format", "target_platforms", "research_required", "experiment_required"}
        reads = set()
        for node in ast.walk(self.func):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and node.value.id == "selection"
            ):
                reads.add(node.attr)
        self.assertEqual(reads, allowed)

    # 70
    def test_candidate_reads_only_allowed_paths(self):
        # Aggregate reads: candidate.selection / candidate.candidate only.
        aggregate_reads = set()
        for node in ast.walk(self.func):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and node.value.id == "candidate"
            ):
                aggregate_reads.add(node.attr)
        self.assertEqual(aggregate_reads, {"selection", "candidate"})

        # Nested DiscoveryCandidate reads (through the bound discovery alias
        # or chained attribute) must be exactly candidate_id/title/content_cluster.
        nested_reads = set()
        for node in ast.walk(self.func):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                if node.attr in {"candidate_id", "title", "content_cluster"}:
                    nested_reads.add(node.attr)
        self.assertEqual(
            nested_reads, {"candidate_id", "title", "content_cluster"}
        )


if __name__ == "__main__":
    unittest.main()
