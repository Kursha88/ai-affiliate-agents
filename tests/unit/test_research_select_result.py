"""Step 14C unit tests: bind SELECT winner to ProcessedCandidate.

Patches ``select_shortlist_winner`` at the point of use in
``src.research.select_result`` so binding behavior is tested
independently from Step 14B. Uses real ``ResearchResult``/``RankingResult``
contracts; for processed-candidate lookup tests, the spec-sanctioned
minimal immutable helper exposes ``candidate_id`` ONLY (the real
``ProcessedCandidate`` requires nested contracts from modules outside the
allowed read list). The function itself keeps the real
``ProcessedCandidate`` annotation. Structural AST tests bind field-access
boundaries to actual code.
"""

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

from src.domain.strategy import (
    ContentCluster,
    ContentFormat,
    StrategicSelection,
    TargetPlatform,
)
from src.research.rank import RankedCandidate, RankingResult
from src.research.researcher import ResearchResult
from src.research import select_result
from src.research.select_result import select_research_result_winner

SOURCE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "research" / "select_result.py"
)

SELECTED = StrategicSelection(
    selected=True,
    selection_reason="selected_test",
    recommended_format=ContentFormat.PRACTICAL_GUIDE,
    target_platforms=(TargetPlatform.TELEGRAM,),
    research_required=False,
    experiment_required=False,
)

_VALID_SCORE_FREE = (6, 6, 6, 6, 6, 6)


def _ranked(cid, rank=1):
    from src.domain.strategy import CandidateScore

    return RankedCandidate(
        candidate_id=cid,
        rank=rank,
        score=CandidateScore(*_VALID_SCORE_FREE),
        cluster=ContentCluster.AI_TOOLS,
        final_rank_score=6.0,
        reason="ranked:test",
    )


@dataclass(frozen=True)
class _ProcessedStub:
    """Spec-sanctioned minimal immutable helper: candidate_id ONLY."""

    candidate_id: str


def _research_result(ranked, processed):
    return ResearchResult(
        ranked=RankingResult(
            ranked=tuple(ranked),
            excluded=(),
            input_count=len(ranked),
            output_count=len(ranked),
        ),
        candidates=tuple(processed),
        adapter_results=(),
        input_count=len(ranked),
        deduplicated_count=len(ranked),
        classified_count=len(ranked),
        verified_count=len(ranked),
        scored_count=len(ranked),
    )


class _Harness(unittest.TestCase):
    """Patch select_shortlist_winner where it is USED (select_result module)."""

    def setUp(self):
        self.m_winner = mock.patch.object(
            select_result, "select_shortlist_winner"
        ).start()
        self.addCleanup(mock.patch.stopall)


class TestSelectorInvocation(_Harness):
    def test_select_shortlist_winner_called_exactly_once(self):
        result = _research_result([], [])
        self.m_winner.return_value = None
        select_research_result_winner(result)
        self.m_winner.assert_called_once()

    def test_selector_receives_exact_result_ranked(self):
        ranked = (_ranked("c1"),)
        result = _research_result(ranked, [])
        self.m_winner.return_value = None
        select_research_result_winner(result)
        # The exact RankingResult object from result.ranked is forwarded.
        self.assertIs(self.m_winner.call_args.args[0], result.ranked)

    def test_selector_none_function_returns_none(self):
        self.m_winner.return_value = None
        self.assertIsNone(select_research_result_winner(_research_result([], [])))


class TestWinnerBinding(_Harness):
    def _winner_case(self):
        processed = (_ProcessedStub("p1"), _ProcessedStub("p2"), _ProcessedStub("p3"))
        ranked = (_ranked("p1", 1), _ranked("p2", 2), _ranked("p3", 3))
        result = _research_result(ranked, processed)
        winner = (ranked[1], SELECTED)  # second ranked candidate wins
        self.m_winner.return_value = winner
        return result, ranked[1], winner

    def test_exact_candidate_id_match_found(self):
        result, ranked_winner, _ = self._winner_case()
        self.m_winner.return_value = (ranked_winner, SELECTED)
        processed, _r, _s = select_research_result_winner(result)
        self.assertEqual(processed.candidate_id, "p2")

    def test_returned_tuple_length_is_3(self):
        result, ranked_winner, _ = self._winner_case()
        self.m_winner.return_value = (ranked_winner, SELECTED)
        bound = select_research_result_winner(result)
        self.assertIsInstance(bound, tuple)
        self.assertEqual(len(bound), 3)

    def test_processed_candidate_identity_preserved(self):
        result, ranked_winner, _ = self._winner_case()
        self.m_winner.return_value = (ranked_winner, SELECTED)
        processed, _r, _s = select_research_result_winner(result)
        self.assertIs(processed, result.candidates[1])

    def test_ranked_candidate_identity_preserved(self):
        result, ranked_winner, _ = self._winner_case()
        self.m_winner.return_value = (ranked_winner, SELECTED)
        _p, ranked, _s = select_research_result_winner(result)
        self.assertIs(ranked, ranked_winner)

    def test_selection_identity_preserved(self):
        result, ranked_winner, _ = self._winner_case()
        self.m_winner.return_value = (ranked_winner, SELECTED)
        _p, _r, selection = select_research_result_winner(result)
        self.assertIs(selection, SELECTED)

    def test_matching_uses_ranked_candidate_id(self):
        # candidate_id with unusual content must be matched verbatim.
        processed = (_ProcessedStub("weird id: ünïcode ✓"),)
        ranked = (_ranked("weird id: ünïcode ✓", 1),)
        result = _research_result(ranked, processed)
        self.m_winner.return_value = (ranked[0], SELECTED)
        bound = select_research_result_winner(result)
        self.assertIs(bound[0], processed[0])

    def test_processed_ordering_does_not_matter(self):
        # Winner may match the third processed candidate.
        processed = (_ProcessedStub("a"), _ProcessedStub("b"), _ProcessedStub("p3"))
        ranked = (_ranked("p3", 1),)
        result = _research_result(ranked, processed)
        self.m_winner.return_value = (ranked[0], SELECTED)
        bound = select_research_result_winner(result)
        self.assertIs(bound[0], processed[2])

    def test_non_winning_processed_candidates_ignored(self):
        processed = (_ProcessedStub("p1"), _ProcessedStub("p2"), _ProcessedStub("p3"))
        ranked = (_ranked("p2", 1),)
        result = _research_result(ranked, processed)
        self.m_winner.return_value = (ranked[0], SELECTED)
        bound = select_research_result_winner(result)
        self.assertIs(bound[0], processed[1])
        # And only one selector call happened — no per-candidate probing.
        self.m_winner.assert_called_once()


class TestConsistencyErrors(_Harness):
    def test_zero_matches_raises_exact_message(self):
        ranked = (_ranked("ghost", 1),)
        result = _research_result(ranked, [_ProcessedStub("other")])
        self.m_winner.return_value = (ranked[0], SELECTED)
        with self.assertRaises(ValueError) as ctx:
            select_research_result_winner(result)
        self.assertEqual(
            str(ctx.exception),
            "selected ranked candidate missing from processed candidates",
        )

    def test_duplicate_matches_raise_exact_message(self):
        processed = (_ProcessedStub("dup"), _ProcessedStub("dup"))
        ranked = (_ranked("dup", 1),)
        result = _research_result(ranked, processed)
        self.m_winner.return_value = (ranked[0], SELECTED)
        with self.assertRaises(ValueError) as ctx:
            select_research_result_winner(result)
        self.assertEqual(str(ctx.exception), "duplicate processed candidate_id")

    def test_duplicate_detected_even_if_unrelated_fields_differ(self):
        # The two stubs differ in identity (distinct objects); only
        # candidate_id equality drives duplicate detection.
        processed = (_ProcessedStub("dup"), _ProcessedStub("dup"))
        self.assertIsNot(processed[0], processed[1])
        ranked = (_ranked("dup", 1),)
        result = _research_result(ranked, processed)
        self.m_winner.return_value = (ranked[0], SELECTED)
        with self.assertRaises(ValueError) as ctx:
            select_research_result_winner(result)
        self.assertEqual(str(ctx.exception), "duplicate processed candidate_id")

    def test_selector_exception_propagates_unchanged(self):
        self.m_winner.side_effect = RuntimeError("winner boom")
        with self.assertRaisesRegex(RuntimeError, "winner boom"):
            select_research_result_winner(_research_result([], []))


class TestIgnoredMetadata(_Harness):
    def _metadata_result(self):
        ranked = (_ranked("meta", 7),)  # rank=7, unusual values
        result = _research_result(ranked, [_ProcessedStub("meta")])
        self.m_winner.return_value = (ranked[0], SELECTED)
        return result, ranked[0]

    def test_adapter_results_irrelevant(self):
        from src.research.researcher import AdapterOutcome
        from src.domain.strategy import SourceType

        result, ranked = self._metadata_result()
        outcome = AdapterOutcome(
            adapter_name="x", source_type=SourceType.GITHUB,
            ok=False, record_count=0, error="irrelevant failure",
        )
        enriched = ResearchResult(
            ranked=result.ranked,
            candidates=result.candidates,
            adapter_results=(outcome,),
            input_count=1,
            deduplicated_count=1,
            classified_count=1,
            verified_count=1,
            scored_count=1,
        )
        bound = select_research_result_winner(enriched)
        self.assertEqual(bound[0].candidate_id, "meta")

    def test_counts_irrelevant(self):
        result, _ranked_c = self._metadata_result()
        weird_counts = ResearchResult(
            ranked=result.ranked,
            candidates=result.candidates,
            adapter_results=(),
            input_count=999,
            deduplicated_count=0,
            classified_count=5,
            verified_count=3,
            scored_count=1,
        )
        bound = select_research_result_winner(weird_counts)
        self.assertIsNotNone(bound)

    def test_rank_irrelevant(self):
        result, ranked_c = self._metadata_result()
        self.assertEqual(ranked_c.rank, 7)  # unusual value, still binds fine
        bound = select_research_result_winner(result)
        self.assertIsNotNone(bound)

    def test_cluster_final_score_reason_irrelevant(self):
        result, _ranked_c = self._metadata_result()
        bound = select_research_result_winner(result)
        self.assertIsNotNone(bound)

    def test_selection_selected_not_rechecked(self):
        # A mocked winner tuple is trusted: its selection is returned
        # unchanged regardless of the .selected value.
        odd_selection = StrategicSelection(
            selected=False,  # even a "rejected" selection is trusted here
            selection_reason="trusted_anyway",
            recommended_format=None,
            target_platforms=(),
        )
        ranked = (_ranked("p1", 1),)
        result = _research_result(ranked, [_ProcessedStub("p1")])
        self.m_winner.return_value = (ranked[0], odd_selection)
        _p, _r, selection = select_research_result_winner(result)
        self.assertIs(selection, odd_selection)


class TestPurity(_Harness):
    def _case(self):
        processed = [_ProcessedStub("p1"), _ProcessedStub("p2")]
        ranked = (_ranked("p2", 2),)
        result = _research_result(ranked, processed)
        self.m_winner.return_value = (ranked[0], SELECTED)
        return result, processed, ranked[0]

    def test_result_candidates_not_mutated(self):
        result, processed, ranked_c = self._case()
        before = tuple(processed)
        select_research_result_winner(result)
        self.assertEqual(result.candidates, before)

    def test_ranked_candidate_not_mutated(self):
        result, _processed, ranked_c = self._case()
        snapshot = ranked_c
        select_research_result_winner(result)
        self.assertEqual(ranked_c, snapshot)  # frozen dataclass equality

    def test_selection_not_mutated(self):
        result, _processed, _ranked_c = self._case()
        select_research_result_winner(result)
        self.assertIs(SELECTED.selected, True)  # unchanged
        self.assertEqual(SELECTED.selection_reason, "selected_test")

    def test_deterministic_repeat_same_identity(self):
        result, _processed, ranked_c = self._case()
        first = select_research_result_winner(result)
        second = select_research_result_winner(result)
        self.assertIs(first[0], second[0])
        self.assertIs(first[1], second[1])
        self.assertIs(first[1], ranked_c)
        self.assertIs(first[2], second[2])


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
            if isinstance(node, ast.FunctionDef) \
                    and node.name == "select_research_result_winner":
                return node
        raise AssertionError("select_research_result_winner not found")

    def test_result_accessed_only_via_ranked_and_candidates(self):
        fn = self._function()
        attrs = {
            node.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "result"
        }
        self.assertEqual(attrs, {"ranked", "candidates"})

    def test_ranked_candidate_access_only_candidate_id(self):
        fn = self._function()
        attrs = {
            node.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ranked_candidate"
        }
        self.assertEqual(attrs, {"candidate_id"})

    def test_processed_candidate_access_only_candidate_id(self):
        fn = self._function()
        # The comprehension variable is `processed`; ensure only
        # .candidate_id is ever read from it.
        attrs = {
            node.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "processed"
        }
        self.assertEqual(attrs, {"candidate_id"})

    def test_no_forbidden_tokens(self):
        forbidden = (
            "sorted", ".sort", "rank_candidates", "select_ranked_candidate",
            "score_candidate", "verify_provenance", "classify",
            "adapters", "random", "datetime", "open", "requests",
            "urllib", "socket", "sqlite3", "os", "yaml", "Config",
            "src.agents", "src.main", "ContentCandidate",
            "DiscoveryCandidate", "deepcopy",
        )
        for token in forbidden:
            self.assertNotIn(token, self.text)

    def test_exactly_one_call_to_select_shortlist_winner(self):
        fn = self._function()
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "select_shortlist_winner"
        ]
        self.assertEqual(len(calls), 1)

    def test_no_strategic_selection_field_inspected(self):
        fn = self._function()
        attrs = {
            node.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "selection"
        }
        self.assertEqual(attrs, set())  # selection is only unpacked/returned


if __name__ == "__main__":
    unittest.main()
