"""Step 14F-A unit tests: ContentCandidate -> legacy news_item bridge.

Tests the NEW ``content_candidate_to_news_item`` with real domain objects
(DiscoveryCandidate, StrategicSelection, CandidateStage, ContentCandidate,
VerificationResult, CandidateScore) and adds regression protection that
``research_result_to_news_item`` remains behaviorally unchanged. Structural
AST tests bind the no-cross-calls / no-new-dependencies boundaries to actual
code (docstring-immune by construction).
"""

import ast
import inspect
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

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
from src.research.legacy_bridge import (
    content_candidate_to_news_item,
    research_result_to_news_item,
)

SOURCE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "research" / "legacy_bridge.py"
)

NOW = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)


def _discovery(**overrides):
    fields = dict(
        candidate_id="cand_x",
        title="VibeWorks CLI released",
        source_type=SourceType.GITHUB,
        source_url="https://github.com/vibeworks/cli",
        discovered_at="2026-09-11T12:00:00+00:00",
        content_cluster=ContentCluster.AI_TOOLS,
        source_name="github",
        published_at="2026-09-11T06:30:00+00:00",  # 5.5h before NOW
        summary="A CLI for vibe coding workflows.",
        raw_score=42.0,
        metadata={"author": "alice"},
    )
    fields.update(overrides)
    return DiscoveryCandidate(**fields)


def _selection(**overrides):
    fields = dict(
        selected=True,
        selection_reason="selected_test",
        recommended_format=ContentFormat.PRACTICAL_GUIDE,
        target_platforms=(TargetPlatform.TELEGRAM,),
        research_required=False,
        experiment_required=False,
    )
    fields.update(overrides)
    return StrategicSelection(**fields)


def _content_candidate(**overrides):
    fields = dict(
        candidate=_discovery(),
        verification=VerificationResult(
            verification_status=VerificationStatus.VERIFIED, confidence=0.9
        ),
        score=CandidateScore(6, 6, 6, 6, 6, 6),
        selection=_selection(),
        stage=CandidateStage.SELECTED,
        content_id=None,
    )
    fields.update(overrides)
    return ContentCandidate(**fields)


class TestMapping(unittest.TestCase):
    def setUp(self):
        self.candidate = _content_candidate()
        self.result = content_candidate_to_news_item(self.candidate, now=NOW)

    def test_returns_dict(self):
        self.assertIsInstance(self.result, dict)

    def test_keys_are_exactly_the_four_legacy_keys(self):
        self.assertEqual(
            set(self.result.keys()), {"title", "source", "url", "age_hours"}
        )

    def test_title_maps_exactly(self):
        self.assertEqual(self.result["title"], "VibeWorks CLI released")

    def test_source_maps_from_source_type_value(self):
        self.assertEqual(self.result["source"], "github")

    def test_url_maps_exactly_without_normalization(self):
        self.assertEqual(self.result["url"], "https://github.com/vibeworks/cli")

    def test_published_at_none_gives_zero_age(self):
        result = content_candidate_to_news_item(
            _content_candidate(candidate=_discovery(published_at=None)), now=NOW
        )
        self.assertEqual(result["age_hours"], 0)

    def test_timezone_aware_iso_string_computes_age(self):
        # 2026-09-11T06:30Z -> 12:00Z == 5.5 hours.
        self.assertEqual(self.result["age_hours"], 5.5)

    def test_timezone_aware_datetime_published_at_computes_age(self):
        # Dataclasses do not enforce annotations at runtime, so a real
        # timezone-aware datetime is accepted exactly like the ISO path.
        result = content_candidate_to_news_item(
            _content_candidate(
                candidate=_discovery(published_at=datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc))
            ),
            now=NOW,
        )
        self.assertEqual(result["age_hours"], 2.0)

    def test_future_published_at_clamps_to_zero(self):
        result = content_candidate_to_news_item(
            _content_candidate(
                candidate=_discovery(published_at="2026-09-11T18:00:00+00:00")
            ),
            now=NOW,
        )
        self.assertEqual(result["age_hours"], 0)

    def test_age_rounds_to_two_decimals(self):
        # 12:00:00 - 10:39:45 == 1.3375h -> 1.34
        result = content_candidate_to_news_item(
            _content_candidate(
                candidate=_discovery(published_at="2026-09-11T10:39:45+00:00")
            ),
            now=NOW,
        )
        self.assertEqual(result["age_hours"], 1.34)


class TestAgeAndTitleErrors(unittest.TestCase):
    def test_naive_now_raises_exact_message(self):
        with self.assertRaises(ValueError) as ctx:
            content_candidate_to_news_item(
                _content_candidate(), now=datetime(2026, 9, 11, 12, 0)
            )
        self.assertEqual(str(ctx.exception), "now must be timezone-aware")

    def test_naive_published_at_string_raises_exact_message(self):
        with self.assertRaises(ValueError) as ctx:
            content_candidate_to_news_item(
                _content_candidate(
                    candidate=_discovery(published_at="2026-09-11T06:30:00")
                ),
                now=NOW,
            )
        self.assertEqual(str(ctx.exception), "published_at must be timezone-aware")

    def test_unsupported_published_at_type_raises_exact_message(self):
        with self.assertRaises(ValueError) as ctx:
            content_candidate_to_news_item(
                _content_candidate(candidate=_discovery(published_at=12345)),
                now=NOW,
            )
        self.assertEqual(str(ctx.exception), "published_at must be timezone-aware")

    def test_empty_title_raises_exact_message(self):
        for bad in ("", "   "):
            with self.subTest(title=bad):
                with self.assertRaises(ValueError) as ctx:
                    content_candidate_to_news_item(
                        _content_candidate(candidate=_discovery(title=bad)), now=NOW
                    )
                self.assertEqual(str(ctx.exception), "ranked candidate title is empty")


class TestPreconditions(unittest.TestCase):
    def test_wrong_stage_raises_exact_message(self):
        with self.assertRaises(ValueError) as ctx:
            content_candidate_to_news_item(
                _content_candidate(stage=CandidateStage.DISCOVERED), now=NOW
            )
        self.assertEqual(str(ctx.exception), "content candidate is not selected")

    def test_none_selection_raises_exact_message(self):
        with self.assertRaises(ValueError) as ctx:
            content_candidate_to_news_item(
                _content_candidate(selection=None), now=NOW
            )
        self.assertEqual(
            str(ctx.exception), "content candidate missing strategic selection"
        )

    def test_unselected_selection_raises_exact_message(self):
        with self.assertRaises(ValueError) as ctx:
            content_candidate_to_news_item(
                _content_candidate(selection=_selection(selected=False)), now=NOW
            )
        self.assertEqual(str(ctx.exception), "strategic selection is not selected")


class TestSelectionFlagsDoNotAffectMapping(unittest.TestCase):
    def test_research_required_true_maps_identically(self):
        baseline = content_candidate_to_news_item(_content_candidate(), now=NOW)
        flagged = content_candidate_to_news_item(
            _content_candidate(selection=_selection(research_required=True)), now=NOW
        )
        self.assertEqual(baseline, flagged)

    def test_experiment_required_true_maps_identically(self):
        baseline = content_candidate_to_news_item(_content_candidate(), now=NOW)
        flagged = content_candidate_to_news_item(
            _content_candidate(selection=_selection(experiment_required=True)), now=NOW
        )
        self.assertEqual(baseline, flagged)


class TestURLPassthrough(unittest.TestCase):
    def test_unicode_query_fragment_url_returned_exactly(self):
        exact = "https://example.com/päth?x=1&y=2#frag"
        result = content_candidate_to_news_item(
            _content_candidate(candidate=_discovery(source_url=exact)), now=NOW
        )
        self.assertEqual(result["url"], exact)
        self.assertIs(result["url"], exact)  # same object: zero processing


class TestPurityAndDeterminism(unittest.TestCase):
    def test_content_candidate_not_mutated(self):
        candidate = _content_candidate()
        snapshot = replace(candidate)
        content_candidate_to_news_item(candidate, now=NOW)
        self.assertEqual(candidate, snapshot)

    def test_discovery_candidate_not_mutated(self):
        discovery = _discovery()
        snapshot = replace(discovery)
        content_candidate_to_news_item(
            _content_candidate(candidate=discovery), now=NOW
        )
        self.assertEqual(discovery, snapshot)

    def test_strategic_selection_not_mutated(self):
        selection = _selection()
        content_candidate_to_news_item(_content_candidate(selection=selection), now=NOW)
        self.assertEqual(selection, _selection())

    def test_deterministic_equal_output(self):
        first = content_candidate_to_news_item(_content_candidate(), now=NOW)
        second = content_candidate_to_news_item(_content_candidate(), now=NOW)
        self.assertEqual(first, second)


# ──────────────────────────────────────────────────────────────────────
# Regression protection for the EXISTING bridge (tests 26-30).
# ──────────────────────────────────────────────────────────────────────

def _strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and \
                    isinstance(node.body[0].value, ast.Constant) and \
                    isinstance(node.body[0].value.value, str):
                node.body = node.body[1:]
    return tree


class TestExistingBridgeRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _strip_docstrings(
            ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
        )

    def _function(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        raise AssertionError(f"{name} not found")

    def test_research_result_to_news_item_still_exists(self):
        self.assertTrue(callable(research_result_to_news_item))

    def test_public_signature_unchanged(self):
        params = inspect.signature(research_result_to_news_item).parameters
        self.assertEqual(list(params.keys()), ["result", "now"])
        self.assertIs(params["result"].kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        self.assertIs(params["now"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_new_function_does_not_call_old_function(self):
        fn = self._function("content_candidate_to_news_item")
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "research_result_to_news_item"
        ]
        self.assertEqual(calls, [])

    def test_old_function_does_not_call_new_function(self):
        fn = self._function("research_result_to_news_item")
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "content_candidate_to_news_item"
        ]
        self.assertEqual(calls, [])

    def test_no_select_stage_dependencies_added(self):
        text = ast.unparse(self.tree)
        forbidden = (
            "run_select_stage", "select_research_result_winner",
            "select_shortlist_winner", "select_ranked_candidate",
            "RankedCandidate", "RankingResult", "Config", "src.main",
            "src.agents", "sqlite3", "random", "yaml", "requests",
            "subprocess", "urllib", "socket",
        )
        for token in forbidden:
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
