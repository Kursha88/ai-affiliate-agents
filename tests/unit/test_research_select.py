"""Step 14A unit tests: deterministic SELECT stage.

Uses the REAL ``RankedCandidate`` type from ``src/research/rank.py``
(constructible without unrelated dependencies via the real
``CandidateScore``). No module mocking. Structural AST tests bind the
"reads ONLY cluster/final_rank_score" and purity guarantees to actual
code (docstring-immune by construction).
"""

import ast
import unittest
from dataclasses import replace
from pathlib import Path

from src.domain.strategy import (
    CandidateScore,
    ContentCluster,
    ContentFormat,
    StrategicSelection,
    TargetPlatform,
)
from src.research.rank import RankedCandidate
from src.research.select import SELECTION_MIN_SCORE, select_ranked_candidate

SOURCE_PATH = Path(__file__).resolve().parents[2] / "src" / "research" / "select.py"

# CandidateScore components chosen so total_score == 5.0 exactly:
# all components equal c -> weighted total == c (weights sum to 1.0).
_SCORE_AT_THRESHOLD = CandidateScore(5, 5, 5, 5, 5, 5)


def _ranked(cluster, final_rank_score=5.0, candidate_id="c1"):
    """Build a real RankedCandidate with the given cluster and score."""
    return RankedCandidate(
        candidate_id=candidate_id,
        rank=1,
        score=_SCORE_AT_THRESHOLD,
        cluster=cluster,
        final_rank_score=final_rank_score,
        reason="ranked:test",
    )


# Exact expected tables (mirroring the spec verbatim).
EXPECTED = {
    ContentCluster.VIBE_CODING: (
        ContentFormat.PRACTICAL_GUIDE,
        (TargetPlatform.TELEGRAM, TargetPlatform.X, TargetPlatform.LINKEDIN,
         TargetPlatform.YOUTUBE_SHORTS, TargetPlatform.TIKTOK),
        False, False, "selected_vibe_coding",
    ),
    ContentCluster.AI_AGENTS: (
        ContentFormat.WORKFLOW,
        (TargetPlatform.TELEGRAM, TargetPlatform.X, TargetPlatform.LINKEDIN),
        False, False, "selected_ai_agents",
    ),
    ContentCluster.AI_TOOLS: (
        ContentFormat.TOOL_DISCOVERY,
        (TargetPlatform.TELEGRAM, TargetPlatform.X, TargetPlatform.LINKEDIN,
         TargetPlatform.PINTEREST),
        False, False, "selected_ai_tools",
    ),
    ContentCluster.AUTOMATION: (
        ContentFormat.WORKFLOW,
        (TargetPlatform.TELEGRAM, TargetPlatform.X, TargetPlatform.LINKEDIN),
        False, False, "selected_automation",
    ),
    ContentCluster.FREE_AI: (
        ContentFormat.COMPARISON,
        (TargetPlatform.TELEGRAM, TargetPlatform.X, TargetPlatform.LINKEDIN,
         TargetPlatform.PINTEREST),
        False, False, "selected_free_ai",
    ),
    ContentCluster.PRACTICAL_EXPERIMENTS: (
        ContentFormat.EXPERIMENT,
        (TargetPlatform.TELEGRAM, TargetPlatform.X, TargetPlatform.LINKEDIN,
         TargetPlatform.YOUTUBE_SHORTS, TargetPlatform.TIKTOK),
        False, True, "selected_practical_experiments",
    ),
    ContentCluster.AI_NEWS: (
        ContentFormat.BREAKING_NEWS,
        (TargetPlatform.TELEGRAM, TargetPlatform.X, TargetPlatform.LINKEDIN),
        True, False, "selected_ai_news",
    ),
}


class TestConstants(unittest.TestCase):
    def test_selection_min_score_is_5(self):
        self.assertIsInstance(SELECTION_MIN_SCORE, float)
        self.assertEqual(SELECTION_MIN_SCORE, 5.0)


class TestRejectionRules(unittest.TestCase):
    def test_missing_cluster_not_selected(self):
        result = select_ranked_candidate(_ranked(None))
        self.assertFalse(result.selected)

    def test_missing_cluster_reason_exact(self):
        result = select_ranked_candidate(_ranked(None))
        self.assertEqual(result.selection_reason, "missing_cluster")

    def test_missing_cluster_rejection_shape(self):
        result = select_ranked_candidate(_ranked(None))
        self.assertIsNone(result.recommended_format)
        self.assertEqual(result.target_platforms, ())
        self.assertIs(result.research_required, False)
        self.assertIs(result.experiment_required, False)

    def test_score_below_threshold_not_selected(self):
        result = select_ranked_candidate(_ranked(ContentCluster.AI_TOOLS, final_rank_score=4.9999))
        self.assertFalse(result.selected)

    def test_below_threshold_reason_exact(self):
        result = select_ranked_candidate(_ranked(ContentCluster.AI_TOOLS, final_rank_score=4.9999))
        self.assertEqual(result.selection_reason, "below_selection_threshold")

    def test_rejected_score_shape(self):
        result = select_ranked_candidate(_ranked(ContentCluster.AI_TOOLS, final_rank_score=4.9999))
        self.assertIsNone(result.recommended_format)
        self.assertEqual(result.target_platforms, ())

    def test_score_exactly_threshold_is_selected(self):
        result = select_ranked_candidate(_ranked(ContentCluster.AI_TOOLS, final_rank_score=5.0))
        self.assertTrue(result.selected)


class TestClusterMapping(unittest.TestCase):
    """Tests 8-14: exact format/platforms/flags/reason for all 7 clusters."""

    def test_vibe_coding_mapping(self):
        result = select_ranked_candidate(_ranked(ContentCluster.VIBE_CODING))
        fmt, platforms, research, experiment, reason = EXPECTED[ContentCluster.VIBE_CODING]
        self.assertTrue(result.selected)
        self.assertIs(result.recommended_format, fmt)
        self.assertEqual(result.target_platforms, platforms)
        self.assertIs(result.research_required, research)
        self.assertIs(result.experiment_required, experiment)
        self.assertEqual(result.selection_reason, reason)

    def test_ai_agents_mapping(self):
        result = select_ranked_candidate(_ranked(ContentCluster.AI_AGENTS))
        fmt, platforms, research, experiment, reason = EXPECTED[ContentCluster.AI_AGENTS]
        self.assertTrue(result.selected)
        self.assertIs(result.recommended_format, fmt)
        self.assertEqual(result.target_platforms, platforms)
        self.assertIs(result.research_required, research)
        self.assertIs(result.experiment_required, experiment)
        self.assertEqual(result.selection_reason, reason)

    def test_ai_tools_mapping(self):
        result = select_ranked_candidate(_ranked(ContentCluster.AI_TOOLS))
        fmt, platforms, research, experiment, reason = EXPECTED[ContentCluster.AI_TOOLS]
        self.assertTrue(result.selected)
        self.assertIs(result.recommended_format, fmt)
        self.assertEqual(result.target_platforms, platforms)
        self.assertIs(result.research_required, research)
        self.assertIs(result.experiment_required, experiment)
        self.assertEqual(result.selection_reason, reason)

    def test_automation_mapping(self):
        result = select_ranked_candidate(_ranked(ContentCluster.AUTOMATION))
        fmt, platforms, research, experiment, reason = EXPECTED[ContentCluster.AUTOMATION]
        self.assertTrue(result.selected)
        self.assertIs(result.recommended_format, fmt)
        self.assertEqual(result.target_platforms, platforms)
        self.assertIs(result.research_required, research)
        self.assertIs(result.experiment_required, experiment)
        self.assertEqual(result.selection_reason, reason)

    def test_free_ai_mapping(self):
        result = select_ranked_candidate(_ranked(ContentCluster.FREE_AI))
        fmt, platforms, research, experiment, reason = EXPECTED[ContentCluster.FREE_AI]
        self.assertTrue(result.selected)
        self.assertIs(result.recommended_format, fmt)
        self.assertEqual(result.target_platforms, platforms)
        self.assertIs(result.research_required, research)
        self.assertIs(result.experiment_required, experiment)
        self.assertEqual(result.selection_reason, reason)

    def test_practical_experiments_mapping(self):
        result = select_ranked_candidate(_ranked(ContentCluster.PRACTICAL_EXPERIMENTS))
        fmt, platforms, research, experiment, reason = EXPECTED[ContentCluster.PRACTICAL_EXPERIMENTS]
        self.assertTrue(result.selected)
        self.assertIs(result.recommended_format, fmt)
        self.assertEqual(result.target_platforms, platforms)
        self.assertIs(result.research_required, research)
        self.assertIs(result.experiment_required, experiment)
        self.assertEqual(result.selection_reason, reason)

    def test_ai_news_mapping(self):
        result = select_ranked_candidate(_ranked(ContentCluster.AI_NEWS))
        fmt, platforms, research, experiment, reason = EXPECTED[ContentCluster.AI_NEWS]
        self.assertTrue(result.selected)
        self.assertIs(result.recommended_format, fmt)
        self.assertEqual(result.target_platforms, platforms)
        self.assertIs(result.research_required, research)
        self.assertIs(result.experiment_required, experiment)
        self.assertEqual(result.selection_reason, reason)


class TestFlags(unittest.TestCase):
    def test_practical_experiments_requires_experiment(self):
        result = select_ranked_candidate(_ranked(ContentCluster.PRACTICAL_EXPERIMENTS))
        self.assertIs(result.experiment_required, True)

    def test_all_other_clusters_no_experiment(self):
        for cluster in ContentCluster:
            if cluster is ContentCluster.PRACTICAL_EXPERIMENTS:
                continue
            with self.subTest(cluster=cluster):
                result = select_ranked_candidate(_ranked(cluster))
                self.assertIs(result.experiment_required, False)

    def test_ai_news_requires_research(self):
        result = select_ranked_candidate(_ranked(ContentCluster.AI_NEWS))
        self.assertIs(result.research_required, True)

    def test_all_other_clusters_no_research(self):
        for cluster in ContentCluster:
            if cluster is ContentCluster.AI_NEWS:
                continue
            with self.subTest(cluster=cluster):
                result = select_ranked_candidate(_ranked(cluster))
                self.assertIs(result.research_required, False)


class TestPlatformOrder(unittest.TestCase):
    def test_platform_tuple_order_exact_for_every_cluster(self):
        for cluster, (_fmt, platforms, _r, _e, _reason) in EXPECTED.items():
            with self.subTest(cluster=cluster):
                result = select_ranked_candidate(_ranked(cluster))
                self.assertEqual(result.target_platforms, platforms)
                # Element-for-element identity check enforces exact order.
                self.assertEqual(len(result.target_platforms), len(platforms))
                for got, expected in zip(result.target_platforms, platforms):
                    self.assertIs(got, expected)


class TestSemanticsAndPurity(unittest.TestCase):
    def test_output_is_real_strategic_selection(self):
        result = select_ranked_candidate(_ranked(ContentCluster.AI_TOOLS))
        self.assertIsInstance(result, StrategicSelection)

    def test_deterministic_same_input_equal_output(self):
        first = select_ranked_candidate(_ranked(ContentCluster.AI_AGENTS, final_rank_score=6.25))
        second = select_ranked_candidate(_ranked(ContentCluster.AI_AGENTS, final_rank_score=6.25))
        self.assertEqual(first, second)

    def test_input_not_mutated(self):
        candidate = _ranked(ContentCluster.FREE_AI, final_rank_score=7.5)
        before = replace(candidate)  # frozen snapshot (raises on mutation attempt)
        select_ranked_candidate(candidate)
        self.assertEqual(candidate, before)

    def test_candidate_id_rank_title_source_not_required(self):
        # Two candidates identical in cluster + score but differing in
        # candidate_id, rank, and free-text reason produce equal output:
        # the selector logic cannot depend on those fields.
        a = RankedCandidate(
            candidate_id="alpha", rank=1, score=_SCORE_AT_THRESHOLD,
            cluster=ContentCluster.AI_TOOLS, final_rank_score=5.0, reason="ranked:a",
        )
        b = RankedCandidate(
            candidate_id="beta", rank=9, score=_SCORE_AT_THRESHOLD,
            cluster=ContentCluster.AI_TOOLS, final_rank_score=5.0, reason="ranked:b",
        )
        self.assertEqual(select_ranked_candidate(a), select_ranked_candidate(b))

    def test_unknown_cluster_raises_value_error(self):
        class _Impostor:
            value = "not_a_real_cluster"

        candidate = RankedCandidate(
            candidate_id="c", rank=1, score=_SCORE_AT_THRESHOLD,
            cluster=_Impostor(),  # non-None, not one of the 7 ContentCluster values
            final_rank_score=5.5, reason="ranked:x",
        )
        with self.assertRaises(ValueError) as ctx:
            select_ranked_candidate(candidate)
        self.assertEqual(str(ctx.exception), "unsupported content cluster")


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees (docstring-immune by construction).
# ──────────────────────────────────────────────────────────────────────

def _code_text(path: Path) -> str:
    """Source with docstrings stripped so scans bind code, not prose."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and \
                    isinstance(node.body[0].value, ast.Constant) and \
                    isinstance(node.body[0].value.value, str):
                node.body = node.body[1:]
    return ast.unparse(tree)


class TestStructuralBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = _code_text(SOURCE_PATH)
        cls.tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))

    def test_selector_reads_only_cluster_and_final_rank_score(self):
        # Every Attribute read on the `candidate` object is exactly one of
        # the two allowed fields.
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "candidate"
            ):
                self.assertIn(node.attr, {"cluster", "final_rank_score"})

    def test_no_forbidden_imports_or_calls(self):
        forbidden_tokens = (
            "random", "datetime", "open", "requests", "urllib", "socket",
            "Config", "Researcher", "score_candidate", "rank_candidates",
            "classify", "verify_provenance", "src.agents", "src.main",
            "sqlite3", "os", "yaml",
        )
        for token in forbidden_tokens:
            self.assertNotIn(token, self.text)

    def test_threshold_constant(self):
        # The constant is declared with an annotation, so scan both
        # ast.Assign and ast.AnnAssign module-level targets.
        values = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name) \
                    and node.targets[0].id == "SELECTION_MIN_SCORE" \
                    and isinstance(node.value, ast.Constant):
                values.append(node.value.value)
            elif isinstance(node, ast.AnnAssign) \
                    and isinstance(node.target, ast.Name) \
                    and node.target.id == "SELECTION_MIN_SCORE" \
                    and isinstance(node.value, ast.Constant):
                values.append(node.value.value)
        self.assertEqual(values, [5.0])


if __name__ == "__main__":
    unittest.main()
