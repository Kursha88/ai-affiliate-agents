"""Step 14E unit tests: SELECT-stage facade over ResearchResult.

Patches both collaborators at the point of use in
``src.research.select_stage`` and uses identity sentinels (``object()``)
so the facade's forwarding behavior is proven independently from Steps
14C/14D. Structural AST tests bind the orchestration-only boundary to
actual code.
"""

import ast
import unittest
from pathlib import Path
from unittest import mock

from src.research import select_stage
from src.research.select_stage import run_select_stage

SOURCE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "research" / "select_stage.py"
)


class _Harness(unittest.TestCase):
    """Patch both callees where they are USED (select_stage module)."""

    def setUp(self):
        # Identity sentinels — the facade must forward objects untouched.
        self.research_result = object()
        self.processed = object()
        self.ranked = object()
        self.selection = object()
        self.content_candidate = object()

        self.m_selector = mock.patch.object(
            select_stage, "select_research_result_winner"
        ).start()
        self.m_builder = mock.patch.object(
            select_stage, "build_selected_content_candidate",
            return_value=self.content_candidate,
        ).start()
        self.addCleanup(mock.patch.stopall)

    def set_winner(self, winner):
        self.m_selector.return_value = winner


class TestSelectorInvocation(_Harness):
    def test_selector_called_exactly_once(self):
        self.set_winner(None)
        run_select_stage(self.research_result)
        self.m_selector.assert_called_once()

    def test_selector_receives_exact_research_result_by_identity(self):
        self.set_winner(None)
        run_select_stage(self.research_result)
        self.assertIs(self.m_selector.call_args.args[0], self.research_result)


class TestNonePath(_Harness):
    def test_selector_none_returns_none(self):
        self.set_winner(None)
        self.assertIsNone(run_select_stage(self.research_result))

    def test_selector_none_builder_not_called(self):
        self.set_winner(None)
        run_select_stage(self.research_result)
        self.m_builder.assert_not_called()


class TestForwardingPath(_Harness):
    def setUp(self):
        super().setUp()
        self.set_winner((self.processed, self.ranked, self.selection))

    def test_builder_called_exactly_once(self):
        run_select_stage(self.research_result)
        self.m_builder.assert_called_once()

    def test_builder_receives_exact_processed_by_identity(self):
        run_select_stage(self.research_result)
        self.assertIs(self.m_builder.call_args.args[0], self.processed)

    def test_builder_receives_exact_selection_by_identity(self):
        run_select_stage(self.research_result)
        self.assertIs(self.m_builder.call_args.args[1], self.selection)

    def test_builder_does_not_receive_ranked_candidate(self):
        run_select_stage(self.research_result)
        all_args = list(self.m_builder.call_args.args) + list(
            self.m_builder.call_args.kwargs.values()
        )
        self.assertNotIn(self.ranked, all_args)

    def test_returns_builder_result_by_identity(self):
        result = run_select_stage(self.research_result)
        self.assertIs(result, self.content_candidate)


class TestExceptionPropagation(_Harness):
    def test_selector_exception_propagates_unchanged(self):
        self.m_selector.side_effect = ValueError("duplicate processed candidate_id")
        with self.assertRaisesRegex(ValueError, "duplicate processed candidate_id"):
            run_select_stage(self.research_result)
        self.m_builder.assert_not_called()

    def test_builder_exception_propagates_unchanged(self):
        self.set_winner((self.processed, self.ranked, self.selection))
        self.m_builder.side_effect = RuntimeError("strategic selection is not selected")
        with self.assertRaisesRegex(
            RuntimeError, "strategic selection is not selected"
        ):
            run_select_stage(self.research_result)


class TestPurity(_Harness):
    def test_ranked_candidate_fields_never_inspected(self):
        # ranked is a plain object(): ANY attribute access would raise
        # AttributeError — proven observationally.
        self.set_winner((self.processed, self.ranked, self.selection))
        result = run_select_stage(self.research_result)
        self.assertIs(result, self.content_candidate)

    def test_processed_fields_never_inspected_directly(self):
        # The facade may only forward processed to the builder.
        self.set_winner((self.processed, self.ranked, self.selection))
        run_select_stage(self.research_result)
        self.m_builder.assert_called_once_with(self.processed, self.selection)

    def test_selection_fields_never_inspected_directly(self):
        # selection is a plain object(): any field access would raise.
        self.set_winner((self.processed, self.ranked, self.selection))
        run_select_stage(self.research_result)

    def test_research_result_not_mutated(self):
        # A Mock with NO attributes: if the facade read result.ranked,
        # result.candidates, adapter_results or any count field, this run
        # would raise AttributeError. It must only forward the object.
        result_without_internals = mock.Mock(spec=[])
        self.set_winner(None)
        self.assertIsNone(run_select_stage(result_without_internals))

    def test_inputs_not_mutated(self):
        # Plain-object inputs + mocked callees: the facade has no way to
        # mutate them, and a successful run proves it never tried.
        self.set_winner((self.processed, self.ranked, self.selection))
        first = run_select_stage(self.research_result)
        second = run_select_stage(self.research_result)
        self.assertIs(first, self.content_candidate)
        self.assertIs(second, self.content_candidate)


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
            if isinstance(node, ast.FunctionDef) and node.name == "run_select_stage":
                return node
        raise AssertionError("run_select_stage not found")

    def test_exactly_one_call_to_select_research_result_winner(self):
        fn = self._function()
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "select_research_result_winner"
        ]
        self.assertEqual(len(calls), 1)

    def test_exactly_one_call_to_build_selected_content_candidate(self):
        fn = self._function()
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "build_selected_content_candidate"
        ]
        self.assertEqual(len(calls), 1)

    def test_no_forbidden_tokens(self):
        forbidden = (
            "select_ranked_candidate", "select_shortlist_winner",
            "rank_candidates", "score_candidate", "verify_provenance",
            "classify", "adapters", "random", "datetime", "open",
            "requests", "urllib", "socket", "sqlite3", "os", "yaml",
            "Config", "src.agents", "src.main", "sorted",
        )
        for token in forbidden:
            self.assertNotIn(token, self.text)

    def test_result_internals_not_accessed(self):
        fn = self._function()
        attrs = {
            node.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "result"
        }
        self.assertEqual(attrs, set())  # result is only forwarded, never read

    def test_ranked_candidate_unpacked_but_never_read(self):
        fn = self._function()
        attrs = [
            node.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ranked_candidate"
        ]
        self.assertEqual(attrs, [])  # assigned/unpacked, zero field reads

    def test_no_selection_field_access(self):
        fn = self._function()
        attrs = [
            node.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "selection"
        ]
        self.assertEqual(attrs, [])

    def test_no_content_candidate_reconstruction(self):
        fn = self._function()
        reconstructions = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ContentCandidate"
        ]
        self.assertEqual(reconstructions, [])
        # And no direct candidate-field assignment/inspection either.
        attrs = [
            node.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "content_candidate"
        ]
        self.assertEqual(attrs, [])


if __name__ == "__main__":
    unittest.main()
