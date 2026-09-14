"""Step 14B unit tests: select ONE winner from the ranked shortlist.

Uses real ``RankingResult``/``RankedCandidate``/``StrategicSelection``
objects and patches ``select_ranked_candidate`` at the point of use in
``src.research.select_winner`` so winner-ordering behavior is tested
independently from Step 14A mapping rules. Structural AST tests bind the
no-sorting / order-preservation / field-access boundaries to actual code.
"""

import ast
import unittest
from pathlib import Path
from unittest import mock

from src.domain.strategy import (
    CandidateScore,
    ContentCluster,
    ContentFormat,
    StrategicSelection,
    TargetPlatform,
)
from src.research.rank import RankedCandidate, RankingResult
from src.research import select_winner
from src.research.select_winner import select_shortlist_winner

SOURCE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "research" / "select_winner.py"
)

SELECTED = StrategicSelection(
    selected=True,
    selection_reason="selected_test",
    recommended_format=ContentFormat.PRACTICAL_GUIDE,
    target_platforms=(TargetPlatform.TELEGRAM,),
    research_required=False,
    experiment_required=False,
)

REJECTED = StrategicSelection(
    selected=False,
    selection_reason="below_selection_threshold",
    recommended_format=None,
    target_platforms=(),
    research_required=False,
    experiment_required=False,
)

_VALID_SCORE = CandidateScore(6, 6, 6, 6, 6, 6)  # total 6.0 — values irrelevant here


def _cand(cid, rank, cluster=ContentCluster.AI_TOOLS, final=9.0):
    return RankedCandidate(
        candidate_id=cid,
        rank=rank,
        score=_VALID_SCORE,
        cluster=cluster,
        final_rank_score=final,
        reason="ranked:test",
    )


def _ranking(candidates):
    """Build a real RankingResult; excluded/count fields are dummy values."""
    candidates = tuple(candidates)
    return RankingResult(
        ranked=candidates,
        excluded=(),
        input_count=len(candidates),
        output_count=len(candidates),
    )


class _SelectorHarness(unittest.TestCase):
    """Patch select_ranked_candidate where it is USED (select_winner module)."""

    def setUp(self):
        self.m_select = mock.patch.object(
            select_winner, "select_ranked_candidate"
        ).start()
        self.addCleanup(mock.patch.stopall)

    def set_outcomes(self, *selections):
        """Map selection outcomes onto candidates in ranked order."""
        self.m_select.side_effect = list(selections)


class TestEmptyShortlist(unittest.TestCase):
    def test_empty_ranked_returns_none(self):
        self.assertIsNone(select_shortlist_winner(_ranking([])))


class TestWinnerIdentity(_SelectorHarness):
    def test_returns_tuple_of_length_2(self):
        c1 = _cand("c1", 1)
        self.set_outcomes(SELECTED)
        result = select_shortlist_winner(_ranking([c1]))
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_returned_candidate_is_same_object_by_identity(self):
        c1 = _cand("c1", 1)
        self.set_outcomes(SELECTED)
        winner, _selection = select_shortlist_winner(_ranking([c1]))
        self.assertIs(winner, c1)

    def test_returned_selection_is_same_object_by_identity(self):
        c1 = _cand("c1", 1)
        self.set_outcomes(SELECTED)
        _winner, selection = select_shortlist_winner(_ranking([c1]))
        self.assertIs(selection, SELECTED)

    def test_first_selected_selector_called_exactly_once(self):
        c1, c2 = _cand("c1", 1), _cand("c2", 2)
        self.set_outcomes(SELECTED)
        select_shortlist_winner(_ranking([c1, c2]))
        self.assertEqual(self.m_select.call_count, 1)
        self.assertEqual(self.m_select.call_args.args, (c1,))

    def test_later_candidates_not_evaluated_after_winner(self):
        c1, c2, c3 = _cand("c1", 1), _cand("c2", 2), _cand("c3", 3)
        self.set_outcomes(SELECTED, REJECTED, REJECTED)
        select_shortlist_winner(_ranking([c1, c2, c3]))
        evaluated = [call.args[0] for call in self.m_select.call_args_list]
        self.assertEqual(evaluated, [c1])


class TestEvaluationOrder(_SelectorHarness):
    def test_first_rejected_second_selected_returns_second(self):
        c1, c2 = _cand("c1", 1), _cand("c2", 2)
        self.set_outcomes(REJECTED, SELECTED)
        winner, _selection = select_shortlist_winner(_ranking([c1, c2]))
        self.assertIs(winner, c2)

    def test_reject_then_select_calls_in_candidate_order(self):
        c1, c2 = _cand("c1", 1), _cand("c2", 2)
        self.set_outcomes(REJECTED, SELECTED)
        select_shortlist_winner(_ranking([c1, c2]))
        evaluated = [call.args[0] for call in self.m_select.call_args_list]
        self.assertEqual(evaluated, [c1, c2])

    def test_two_rejected_third_selected_returns_third(self):
        c1, c2, c3 = _cand("c1", 1), _cand("c2", 2), _cand("c3", 3)
        self.set_outcomes(REJECTED, REJECTED, SELECTED)
        winner, _selection = select_shortlist_winner(_ranking([c1, c2, c3]))
        self.assertIs(winner, c3)

    def test_all_rejected_returns_none(self):
        c1, c2 = _cand("c1", 1), _cand("c2", 2)
        self.set_outcomes(REJECTED, REJECTED)
        self.assertIsNone(select_shortlist_winner(_ranking([c1, c2])))

    def test_all_rejected_selector_called_once_per_candidate(self):
        c1, c2, c3 = _cand("c1", 1), _cand("c2", 2), _cand("c3", 3)
        self.set_outcomes(REJECTED, REJECTED, REJECTED)
        select_shortlist_winner(_ranking([c1, c2, c3]))
        self.assertEqual(self.m_select.call_count, 3)


class TestOrderSemantics(_SelectorHarness):
    def test_lower_score_first_in_tuple_still_wins(self):
        # ranking.ranked order is authoritative — NOT final_rank_score.
        low_first = _cand("low", 1, final=5.0)
        high_second = _cand("high", 2, final=9.9)
        self.set_outcomes(SELECTED, REJECTED)
        winner, _ = select_shortlist_winner(_ranking([low_first, high_second]))
        self.assertIs(winner, low_first)

    def test_rank_out_of_numeric_order_tuple_controls_evaluation(self):
        # .rank values deliberately out of numeric order in the tuple.
        third = _cand("r3", 3)
        first = _cand("r1", 1)
        second = _cand("r2", 2)
        self.set_outcomes(REJECTED, SELECTED, REJECTED)
        winner, _ = select_shortlist_winner(_ranking([third, first, second]))
        self.assertIs(winner, first)  # second tuple element wins
        evaluated = [call.args[0] for call in self.m_select.call_args_list]
        self.assertEqual(evaluated, [third, first])  # third was evaluated first

    def test_candidate_id_does_not_affect_winner_logic(self):
        a = _cand("zzz-last-alphabetically", 2)
        b = _cand("aaa-first-alphabetically", 1)
        self.set_outcomes(SELECTED, REJECTED)
        winner, _ = select_shortlist_winner(_ranking([a, b]))
        self.assertIs(winner, a)  # tuple order, not candidate_id

    def test_cluster_does_not_directly_affect_winner_logic(self):
        news_first = _cand("news", 1, cluster=ContentCluster.AI_NEWS)
        tools_second = _cand("tools", 2, cluster=ContentCluster.AI_TOOLS)
        self.set_outcomes(SELECTED, REJECTED)
        winner, _ = select_shortlist_winner(_ranking([news_first, tools_second]))
        self.assertIs(winner, news_first)  # ai_news is fully selectable in tuple order

    def test_final_rank_score_does_not_directly_affect_winner_logic(self):
        c1 = _cand("c1", 1, final=0.5)
        c2 = _cand("c2", 2, final=10.0)
        self.set_outcomes(SELECTED, REJECTED)
        winner, _ = select_shortlist_winner(_ranking([c1, c2]))
        self.assertIs(winner, c1)


class TestExceptionPropagation(_SelectorHarness):
    def test_selector_exception_on_first_candidate_propagates(self):
        c1 = _cand("c1", 1)
        self.m_select.side_effect = ValueError("unsupported content cluster")
        with self.assertRaisesRegex(ValueError, "unsupported content cluster"):
            select_shortlist_winner(_ranking([c1]))

    def test_selector_exception_on_later_candidate_propagates(self):
        c1, c2, c3 = _cand("c1", 1), _cand("c2", 2), _cand("c3", 3)
        self.set_outcomes(REJECTED, REJECTED)
        self.m_select.side_effect = RuntimeError("selector boom")
        with self.assertRaisesRegex(RuntimeError, "selector boom"):
            select_shortlist_winner(_ranking([c1, c2, c3]))

    def test_after_exception_later_candidates_not_evaluated(self):
        c1, c2, c3 = _cand("c1", 1), _cand("c2", 2), _cand("c3", 3)

        def _select(candidate):
            if candidate is c1:
                return REJECTED  # first candidate evaluated and rejected
            raise RuntimeError("boom")  # second candidate raises

        self.m_select.side_effect = _select
        with self.assertRaises(RuntimeError):
            select_shortlist_winner(_ranking([c1, c2, c3]))
        evaluated = [call.args[0] for call in self.m_select.call_args_list]
        self.assertEqual(evaluated, [c1, c2])  # c3 never reached


class TestRankingMetadataIgnored(unittest.TestCase):
    """excluded / input_count / output_count must not influence the winner."""

    def _ranking_with_metadata(self):
        selected_cand = _cand("winner", 1)
        excluded = _cand("excluded-x", 0)
        ranking = RankingResult(
            ranked=(selected_cand,),
            excluded=(_cand("excluded-1", 0), excluded),
            input_count=99,
            output_count=1,
        )
        return ranking, selected_cand

    @mock.patch("src.research.select_winner.select_ranked_candidate")
    def test_excluded_is_ignored(self, m_select):
        ranking, winner = self._ranking_with_metadata()
        m_select.return_value = SELECTED
        result_winner, _ = select_shortlist_winner(ranking)
        self.assertIs(result_winner, winner)
        evaluated = [call.args[0] for call in m_select.call_args_list]
        self.assertNotIn(ranking.excluded[0], evaluated)
        self.assertNotIn(ranking.excluded[1], evaluated)

    @mock.patch("src.research.select_winner.select_ranked_candidate")
    def test_input_count_is_ignored(self, m_select):
        ranking, _winner = self._ranking_with_metadata()
        m_select.return_value = REJECTED
        # input_count=99 with one ranked entry: if counts were used, results
        # would differ; function must return None based only on selections.
        self.assertIsNone(select_shortlist_winner(ranking))

    @mock.patch("src.research.select_winner.select_ranked_candidate")
    def test_output_count_is_ignored(self, m_select):
        ranking, _winner = self._ranking_with_metadata()
        m_select.return_value = REJECTED
        self.assertIsNone(select_shortlist_winner(ranking))


class TestSelectionContract(_SelectorHarness):
    def test_rejection_decision_uses_only_selected_flag(self):
        # A rejected selection carrying non-empty content must still be
        # treated as rejected: only .selected drives the decision.
        odd_rejection = StrategicSelection(
            selected=False,
            selection_reason="whatever",
            recommended_format=ContentFormat.WORKFLOW,  # non-None on a rejection
            target_platforms=(TargetPlatform.X,),
            research_required=True,
            experiment_required=True,
        )
        c1 = _cand("c1", 1)
        self.set_outcomes(odd_rejection)
        self.assertIsNone(select_shortlist_winner(_ranking([c1])))

    def test_selected_selection_returned_unchanged(self):
        arbitrary_selection = StrategicSelection(
            selected=True,
            selection_reason="selected_test",
            recommended_format=ContentFormat.EXPERIMENT,
            target_platforms=(TargetPlatform.TIKTOK, TargetPlatform.PINTEREST),
            research_required=True,
            experiment_required=True,
        )
        c1 = _cand("c1", 1)
        self.set_outcomes(arbitrary_selection)
        _winner, selection = select_shortlist_winner(_ranking([c1]))
        self.assertIs(selection, arbitrary_selection)

    def test_deterministic_repeat_same_outcome(self):
        c1, c2 = _cand("c1", 1), _cand("c2", 2)
        ranking = _ranking([c1, c2])
        self.set_outcomes(REJECTED, SELECTED)
        first = select_shortlist_winner(ranking)
        self.set_outcomes(REJECTED, SELECTED)
        second = select_shortlist_winner(ranking)
        self.assertIs(first[0], second[0])
        self.assertIs(first[0], c2)
        self.assertIs(first[1], second[1])


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees (docstring-immune by construction).
# ──────────────────────────────────────────────────────────────────────

def _code_text(path: Path) -> str:
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

    def _function(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == "select_shortlist_winner":
                return node
        raise AssertionError("select_shortlist_winner not found")

    def test_no_forbidden_tokens(self):
        forbidden = (
            "sorted", ".sort", "rank_candidates", "score_candidate",
            "verify_provenance", "classify", "random", "datetime",
            "open", "requests", "urllib", "socket", "sqlite3", "os",
            "yaml", "Config", "Researcher", "src.agents", "src.main",
        )
        for token in forbidden:
            self.assertNotIn(token, self.text)

    def test_iterates_ranking_ranked(self):
        fn = self._function()
        loops = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
        self.assertEqual(len(loops), 1)
        target = loops[0].iter
        self.assertIsInstance(target, ast.Attribute)
        self.assertEqual(target.attr, "ranked")
        self.assertIsInstance(target.value, ast.Name)
        self.assertEqual(target.value.id, "ranking")

    def test_only_direct_selection_decision_is_selected_flag(self):
        fn = self._function()
        attribute_reads = {
            node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)
        }
        self.assertEqual(attribute_reads, {"selected", "ranked"})

    def test_candidate_fields_not_accessed_directly(self):
        fn = self._function()
        # The loop variable `candidate` may only be passed to the selector.
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id == "candidate":
                self.fail(f"direct candidate field access: candidate.{node.attr}")

    def test_selector_called_inside_loop(self):
        fn = self._function()
        loop = next(n for n in ast.walk(fn) if isinstance(n, ast.For))

        def contains_call_on_candidate(node):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "select_ranked_candidate":
                    if node.args and isinstance(node.args[0], ast.Name) \
                            and node.args[0].id == "candidate":
                        return True
            return any(contains_call_on_candidate(child) for child in ast.iter_child_nodes(node))

        self.assertTrue(any(contains_call_on_candidate(child) for child in loop.body))


if __name__ == "__main__":
    unittest.main()
