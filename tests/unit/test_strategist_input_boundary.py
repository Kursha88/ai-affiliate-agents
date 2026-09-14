"""Step 15B — validated ContentCandidate → StrategistInput boundary.

Tests use REAL domain types (ContentCandidate, DiscoveryCandidate,
StrategicSelection, CandidateStage, enums). The smallest valid fixture is
used: VerificationResult defaults and score=None are fine because this
boundary must ignore them.
"""

import ast
import dataclasses
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
from src.domain.strategist import StrategistInput
from src.strategy.strategist_input import build_strategist_input

MODULE_PATH = Path("src/strategy/strategist_input.py")


_UNSET = object()  # distinguishes "not provided" from explicit selection=None


def make_candidate(
    *,
    stage=CandidateStage.SELECTED,
    selection=_UNSET,
    cluster=ContentCluster.VIBE_CODING,
    selection_reason="selected_test",
    score=None,
    content_id=None,
) -> ContentCandidate:
    """Build the smallest valid real ContentCandidate fixture.

    Omitting ``selection`` builds a valid selected StrategicSelection;
    passing ``selection=None`` explicitly produces a candidate with no
    selection (a legal ContentCandidate state).
    """
    if selection is _UNSET:
        selection = StrategicSelection(
            selected=True,
            selection_reason=selection_reason,
            recommended_format=ContentFormat.PRACTICAL_GUIDE,
            target_platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
            research_required=False,
            experiment_required=False,
        )
    discovery = DiscoveryCandidate(
        candidate_id="cand-1",
        title="Test candidate",
        source_type=SourceType.GITHUB,
        source_url="https://github.com/owner/repo",
        discovered_at="2026-09-14T00:00:00+00:00",
        content_cluster=cluster,
    )
    return ContentCandidate(
        candidate=discovery,
        verification=VerificationResult(),
        score=score,
        selection=selection,
        stage=stage,
        content_id=content_id,
    )


class TestSuccessContract(unittest.TestCase):
    """Tests 1-13."""

    def setUp(self):
        self.candidate = make_candidate()

    # 1
    def test_returns_real_strategist_input(self):
        result = build_strategist_input(self.candidate)
        self.assertIsInstance(result, StrategistInput)

    # 2
    def test_preserves_exact_candidate_identity(self):
        result = build_strategist_input(self.candidate)
        self.assertIs(result.content_candidate, self.candidate)

    # 3
    def test_selected_stage_passes(self):
        result = build_strategist_input(self.candidate)
        self.assertIs(result.content_candidate.stage, CandidateStage.SELECTED)

    # 4
    def test_selected_true_passes(self):
        candidate = make_candidate(
            selection=StrategicSelection(
                selected=True,
                selection_reason="r",
                recommended_format=ContentFormat.WORKFLOW,
                target_platforms=(TargetPlatform.X,),
            )
        )
        result = build_strategist_input(candidate)
        self.assertIs(result.content_candidate.selection.selected, True)

    # 5
    def test_real_recommended_format_passes_unchanged(self):
        for fmt in (
            ContentFormat.PRACTICAL_GUIDE,
            ContentFormat.BREAKING_NEWS,
            ContentFormat.COMPARISON,
            ContentFormat.EXPERIMENT,
            ContentFormat.WORKFLOW,
        ):
            with self.subTest(format=fmt):
                candidate = make_candidate(
                    selection=StrategicSelection(
                        selected=True,
                        selection_reason="r",
                        recommended_format=fmt,
                        target_platforms=(TargetPlatform.X,),
                    )
                )
                result = build_strategist_input(candidate)
                self.assertIs(
                    result.content_candidate.selection.recommended_format, fmt
                )

    # 6
    def test_one_target_platform_passes(self):
        candidate = make_candidate(
            selection=StrategicSelection(
                selected=True,
                selection_reason="r",
                recommended_format=ContentFormat.WORKFLOW,
                target_platforms=(TargetPlatform.TELEGRAM,),
            )
        )
        result = build_strategist_input(candidate)
        self.assertEqual(
            result.content_candidate.selection.target_platforms,
            (TargetPlatform.TELEGRAM,),
        )

    # 7
    def test_multiple_target_platforms_pass(self):
        candidate = make_candidate(
            selection=StrategicSelection(
                selected=True,
                selection_reason="r",
                recommended_format=ContentFormat.WORKFLOW,
                target_platforms=(
                    TargetPlatform.TELEGRAM,
                    TargetPlatform.LINKEDIN,
                    TargetPlatform.PINTEREST,
                ),
            )
        )
        result = build_strategist_input(candidate)
        self.assertEqual(
            result.content_candidate.selection.target_platforms,
            (
                TargetPlatform.TELEGRAM,
                TargetPlatform.LINKEDIN,
                TargetPlatform.PINTEREST,
            ),
        )

    # 8
    def test_platform_order_irrelevant_and_unmodified(self):
        platforms = (TargetPlatform.PINTEREST, TargetPlatform.TELEGRAM)
        candidate = make_candidate(
            selection=StrategicSelection(
                selected=True,
                selection_reason="r",
                recommended_format=ContentFormat.WORKFLOW,
                target_platforms=platforms,
            )
        )
        result = build_strategist_input(candidate)
        self.assertIs(
            result.content_candidate.selection.target_platforms, platforms
        )
        self.assertEqual(
            result.content_candidate.selection.target_platforms,
            (TargetPlatform.PINTEREST, TargetPlatform.TELEGRAM),
        )

    # 9
    def test_real_content_cluster_passes(self):
        for cluster in ContentCluster:
            with self.subTest(cluster=cluster):
                candidate = make_candidate(cluster=cluster)
                result = build_strategist_input(candidate)
                self.assertIs(
                    result.content_candidate.candidate.content_cluster, cluster
                )

    # 10-13: the four research/experiment flag combinations.
    def test_research_and_experiment_flags_pass(self):
        for research in (False, True):
            for experiment in (False, True):
                with self.subTest(research=research, experiment=experiment):
                    candidate = make_candidate(
                        selection=StrategicSelection(
                            selected=True,
                            selection_reason="r",
                            recommended_format=ContentFormat.WORKFLOW,
                            target_platforms=(TargetPlatform.X,),
                            research_required=research,
                            experiment_required=experiment,
                        )
                    )
                    result = build_strategist_input(candidate)
                    self.assertIs(
                        result.content_candidate.selection.research_required,
                        research,
                    )
                    self.assertIs(
                        result.content_candidate.selection.experiment_required,
                        experiment,
                    )


class TestErrorContract(unittest.TestCase):
    """Tests 14-21: exact ValueError messages."""

    # 14-16: wrong stage raises the exact stage error.
    def test_wrong_stage_raises_exact_error(self):
        for stage in (
            CandidateStage.DISCOVERED,
            CandidateStage.SCORED,
            CandidateStage.RESEARCH_EXPERIMENT,
        ):
            with self.subTest(stage=stage):
                candidate = make_candidate(stage=stage)
                with self.assertRaises(ValueError) as ctx:
                    build_strategist_input(candidate)
                self.assertEqual(
                    str(ctx.exception),
                    "content candidate is not at selected stage",
                )

    # 17
    def test_missing_selection_raises_exact_error(self):
        candidate = make_candidate(selection=None)
        with self.assertRaises(ValueError) as ctx:
            build_strategist_input(candidate)
        self.assertEqual(
            str(ctx.exception),
            "content candidate missing strategic selection",
        )

    # 18
    def test_not_selected_raises_exact_error(self):
        candidate = make_candidate(
            selection=StrategicSelection(
                selected=False,
                selection_reason="below_selection_threshold",
                recommended_format=None,
                target_platforms=(),
            )
        )
        with self.assertRaises(ValueError) as ctx:
            build_strategist_input(candidate)
        self.assertEqual(
            str(ctx.exception),
            "strategic selection is not selected",
        )

    # 19
    def test_missing_format_raises_exact_error(self):
        candidate = make_candidate(
            selection=StrategicSelection(
                selected=True,
                selection_reason="r",
                recommended_format=None,
                target_platforms=(TargetPlatform.X,),
            )
        )
        with self.assertRaises(ValueError) as ctx:
            build_strategist_input(candidate)
        self.assertEqual(
            str(ctx.exception),
            "strategic selection missing recommended format",
        )

    # 20
    def test_missing_platforms_raises_exact_error(self):
        candidate = make_candidate(
            selection=StrategicSelection(
                selected=True,
                selection_reason="r",
                recommended_format=ContentFormat.WORKFLOW,
                target_platforms=(),
            )
        )
        with self.assertRaises(ValueError) as ctx:
            build_strategist_input(candidate)
        self.assertEqual(
            str(ctx.exception),
            "strategic selection missing target platforms",
        )

    # 21
    def test_missing_cluster_raises_exact_error(self):
        candidate = make_candidate(cluster=None)
        with self.assertRaises(ValueError) as ctx:
            build_strategist_input(candidate)
        self.assertEqual(
            str(ctx.exception),
            "content candidate missing content cluster",
        )


class TestValidationOrder(unittest.TestCase):
    """Tests 22-26: earlier invariants win over later ones."""

    # 22
    def test_stage_error_wins_over_missing_selection(self):
        candidate = make_candidate(stage=CandidateStage.DISCOVERED, selection=None)
        with self.assertRaises(ValueError) as ctx:
            build_strategist_input(candidate)
        self.assertEqual(
            str(ctx.exception),
            "content candidate is not at selected stage",
        )

    # 23
    def test_missing_selection_wins_over_other_invalid_state(self):
        # selection=None plus an empty cluster — the selection error must win.
        candidate = make_candidate(selection=None, cluster=None)
        with self.assertRaises(ValueError) as ctx:
            build_strategist_input(candidate)
        self.assertEqual(
            str(ctx.exception),
            "content candidate missing strategic selection",
        )

    # 24
    def test_selected_error_wins_over_missing_format(self):
        candidate = make_candidate(
            selection=StrategicSelection(
                selected=False,
                selection_reason="r",
                recommended_format=None,
                target_platforms=(),
            )
        )
        with self.assertRaises(ValueError) as ctx:
            build_strategist_input(candidate)
        self.assertEqual(
            str(ctx.exception),
            "strategic selection is not selected",
        )

    # 25
    def test_format_error_wins_over_missing_platforms(self):
        candidate = make_candidate(
            selection=StrategicSelection(
                selected=True,
                selection_reason="r",
                recommended_format=None,
                target_platforms=(),
            )
        )
        with self.assertRaises(ValueError) as ctx:
            build_strategist_input(candidate)
        self.assertEqual(
            str(ctx.exception),
            "strategic selection missing recommended format",
        )

    # 26
    def test_platforms_error_wins_over_missing_cluster(self):
        candidate = make_candidate(
            selection=StrategicSelection(
                selected=True,
                selection_reason="r",
                recommended_format=ContentFormat.WORKFLOW,
                target_platforms=(),
            ),
            cluster=None,
        )
        with self.assertRaises(ValueError) as ctx:
            build_strategist_input(candidate)
        self.assertEqual(
            str(ctx.exception),
            "strategic selection missing target platforms",
        )


class TestPurityAndIgnoredFields(unittest.TestCase):
    """Tests 27-36."""

    # 27
    def test_selection_reason_does_not_affect_success(self):
        for reason in ("", "below_selection_threshold", "irrelevant text"):
            with self.subTest(reason=reason):
                candidate = make_candidate(selection_reason=reason)
                result = build_strategist_input(candidate)
                self.assertIs(result.content_candidate, candidate)

    # 28
    def test_score_none_does_not_affect_success(self):
        result = build_strategist_input(make_candidate(score=None))
        self.assertIsNone(result.content_candidate.score)
        self.assertIs(result.content_candidate.candidate, result.content_candidate.candidate)
        self.assertTrue(result.content_candidate.stage is CandidateStage.SELECTED)

    # 29
    def test_verification_value_does_not_affect_success(self):
        for verification in (
            VerificationResult(),  # unverified defaults
            VerificationResult(
                verification_status=__import__(
                    "src.domain.strategy", fromlist=["VerificationStatus"]
                ).VerificationStatus.VERIFIED,
                primary_source_found=True,
                primary_source_url="https://example.com/src",
                confidence=0.95,
                notes="ok",
            ),
        ):
            with self.subTest(status=verification.verification_status):
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
                    verification=verification,
                    score=None,
                    selection=StrategicSelection(
                        selected=True,
                        selection_reason="r",
                        recommended_format=ContentFormat.WORKFLOW,
                        target_platforms=(TargetPlatform.X,),
                    ),
                    stage=CandidateStage.SELECTED,
                )
                result = build_strategist_input(candidate)
                self.assertIs(result.content_candidate, candidate)

    # 30-31: content_id both ways.
    def test_content_id_does_not_affect_success(self):
        for content_id in (None, "content-42"):
            with self.subTest(content_id=content_id):
                candidate = make_candidate(content_id=content_id)
                result = build_strategist_input(candidate)
                self.assertIs(result.content_candidate, candidate)

    # 32-35: no mutation of any input object.
    def test_no_mutation_of_inputs(self):
        selection = StrategicSelection(
            selected=True,
            selection_reason="r",
            recommended_format=ContentFormat.PRACTICAL_GUIDE,
            target_platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
            research_required=False,
            experiment_required=False,
        )
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
        candidate_before = candidate
        selection_before = selection
        discovery_before = discovery
        platforms_before = selection.target_platforms

        result = build_strategist_input(candidate)

        # All objects are frozen dataclasses — identical untouched objects.
        self.assertIs(result.content_candidate, candidate_before)
        self.assertIs(result.content_candidate.selection, selection_before)
        self.assertIs(result.content_candidate.candidate, discovery_before)
        self.assertIs(result.content_candidate.selection.target_platforms, platforms_before)
        self.assertEqual(result.content_candidate, candidate_before)
        self.assertEqual(result.content_candidate.selection, selection_before)
        self.assertEqual(result.content_candidate.candidate, discovery_before)

        # Direct frozen writes would raise; prove immutability explicitly.
        with self.assertRaises(dataclasses.FrozenInstanceError):
            candidate.stage = CandidateStage.DISCOVERED
        with self.assertRaises(dataclasses.FrozenInstanceError):
            selection.selected = False

    # 36
    def test_deterministic_identity(self):
        candidate = make_candidate()
        first = build_strategist_input(candidate)
        second = build_strategist_input(candidate)
        self.assertIs(first.content_candidate, candidate)
        self.assertIs(second.content_candidate, candidate)
        self.assertIs(first.content_candidate, second.content_candidate)


class TestStructuralBoundaries(unittest.TestCase):
    """Tests 37-50: AST/introspection structural guarantees."""

    @classmethod
    def setUpClass(cls):
        cls.source = MODULE_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.func = next(
            node
            for node in ast.walk(cls.tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "build_strategist_input"
        )

    def _modules(self):
        modules = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name)
        return modules

    def _imported_top_names(self):
        names = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    names.add((alias.asname or alias.name).split(".")[0])
        return names

    # 37
    def test_all_exports_exact(self):
        import src.strategy.strategist_input as module

        self.assertEqual(list(module.__all__), ["build_strategist_input"])

    # 38
    def test_exactly_one_public_function(self):
        top_level_functions = [
            node.name
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef)
        ]
        self.assertEqual(top_level_functions, ["build_strategist_input"])
        self.assertTrue(
            top_level_functions[0].startswith("build_")
            and not top_level_functions[0].startswith("_")
        )

    # 39
    def test_no_strategist_plan_reference(self):
        self.assertNotIn("StrategistPlan", self.source)

    # 40
    def test_no_format_or_platform_defaults(self):
        self.assertNotIn("ContentFormat.WORKFLOW =", self.source)
        self.assertNotIn("TargetPlatform.TELEGRAM =", self.source)
        # No assignment of a format/platform constant anywhere in the function.
        for node in ast.walk(self.func):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.assertNotIn(
                            "format", target.id.lower()
                        )
                        self.assertNotIn(
                            "platform", target.id.lower()
                        )
        # No literal format/platform fallback inside the function body.
        self.assertNotIn("TargetPlatform", ast.unparse(self.func))
        self.assertNotIn("ContentFormat", ast.unparse(self.func))

    # 41
    def test_no_select_calls_or_imports(self):
        self.assertNotIn("select_", self.source)

    # 42
    def test_no_scoring_verification_research_imports(self):
        self.assertEqual(self._modules() & {"src.research"}, set())
        for banned in ("score", "verification", "research"):
            self.assertNotIn(f"from src.{banned}", self.source)
        # No research-modules import names at all.
        for name in self._imported_top_names():
            self.assertNotIn("research", name)

    # 43
    def test_no_config_main_agents_imports(self):
        self.assertEqual(
            self._modules() & {"src.main", "src.agents", "src.core.config"},
            set(),
        )
        self.assertNotIn("Config", self._imported_top_names())

    # 44
    def test_no_utility_imports(self):
        modules = self._modules()
        for banned in (
            "datetime",
            "random",
            "os",
            "pathlib",
            "yaml",
            "requests",
        ):
            self.assertNotIn(banned, modules)
            self.assertNotIn(banned, self._imported_top_names())

    # 45
    def test_no_try_except_in_function(self):
        for node in ast.walk(self.func):
            self.assertNotIsInstance(node, ast.Try)

    # 46
    def test_no_mutation_assignments(self):
        # No attribute-store anywhere in the function.
        for node in ast.walk(self.func):
            if isinstance(node, ast.Attribute):
                self.assertNotIsInstance(node.ctx, ast.Store)

    # 47
    def test_content_candidate_read_only_through_allowed_fields(self):
        allowed = {"stage", "selection", "candidate"}
        reads = set()
        for node in ast.walk(self.func):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and node.value.id == "content_candidate"
            ):
                reads.add(node.attr)
        self.assertEqual(reads, allowed)

    # 48
    def test_selection_read_only_through_allowed_fields(self):
        allowed = {"selected", "recommended_format", "target_platforms"}
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

    # 49
    def test_forbidden_field_reads_absent(self):
        # Scan CODE ONLY: re-parse and strip all docstrings first, so the
        # module docstring's documentation of deliberately-ignored fields
        # cannot trip the scan.
        stripped = ast.parse(self.source)
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
        source_no_strings = ast.unparse(stripped)
        for banned in (
            "research_required",
            "experiment_required",
            "selection_reason",
            ".score",
            ".verification",
            "content_id",
        ):
            self.assertNotIn(banned, source_no_strings)

    # 50
    def test_strategist_input_constructed_exactly_once(self):
        constructions = [
            node
            for node in ast.walk(self.func)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "StrategistInput"
        ]
        self.assertEqual(len(constructions), 1)


if __name__ == "__main__":
    unittest.main()
