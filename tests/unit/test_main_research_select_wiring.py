"""Step 14F-B unit tests: production Step 0 switched to the SELECT-stage path.

Patches every dependency WHERE USED in ``src.main`` (Config, run_live_research,
run_select_stage, content_candidate_to_news_item, get_fallback_topic) and
tests ``_get_production_discovery`` directly — no full pipeline run, no
network, no DB. Structural AST tests are focused around the imports and
``_get_production_discovery`` only (no whole-file snapshot).

Step 15G-A-FIX migration: the helper now returns the immutable
``_ProductionDiscovery`` (selected_candidate / news_item / used_fallback)
instead of a bare news_item dict.
"""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import src.main as main_module
from src.main import _get_production_discovery

SOURCE_PATH = Path(__file__).resolve().parents[2] / "src" / "main.py"

NOW = object()  # identity sentinel: the helper must forward, never inspect
RESEARCH_RESULT = object()
SELECTED_CANDIDATE = object()
NEWS_ITEM = {"title": "Selected Winner", "source": "github",
             "url": "https://example.com/winner", "age_hours": 1.5}
FALLBACK_ITEM = {"title": "Fallback Topic", "source": "editorial",
                 "url": "", "age_hours": 0}
LIVE_KWARGS = {
    "blog_feeds": ("blog",),
    "docs_feeds": ("docs",),
    "trusted_primary_domains": ("example.com",),
}


def _fake_config():
    config = mock.Mock()
    config.live_kwargs.return_value = dict(LIVE_KWARGS)
    return config


class _Harness(unittest.TestCase):
    """Patch all production dependencies at their point of use in src.main."""

    def setUp(self):
        self.config = _fake_config()
        self.m_config = mock.patch.object(
            main_module, "Config",
            **{"get_research_config.return_value": self.config},
        ).start()
        self.m_run_live = mock.patch.object(
            main_module, "run_live_research", return_value=RESEARCH_RESULT
        ).start()
        self.m_select = mock.patch.object(
            main_module, "run_select_stage", return_value=SELECTED_CANDIDATE
        ).start()
        self.m_bridge = mock.patch.object(
            main_module, "content_candidate_to_news_item",
            return_value=dict(NEWS_ITEM),
        ).start()
        self.m_fallback = mock.patch.object(
            main_module, "get_fallback_topic", return_value=dict(FALLBACK_ITEM)
        ).start()
        self.log = mock.Mock()
        self.addCleanup(mock.patch.stopall)

    def run_helper(self):
        return _get_production_discovery(now=NOW, log=self.log)


class TestSuccessfulSelectPath(_Harness):
    def test_config_get_research_config_called_once(self):
        self.run_helper()
        self.m_config.get_research_config.assert_called_once()

    def test_run_live_research_called_once(self):
        self.run_helper()
        self.m_run_live.assert_called_once()

    def test_run_live_research_receives_exact_now(self):
        self.run_helper()
        self.assertIs(self.m_run_live.call_args.kwargs["now"], NOW)

    def test_run_live_research_receives_limit_5(self):
        self.run_helper()
        self.assertEqual(self.m_run_live.call_args.kwargs["limit"], 5)

    def test_live_kwargs_forwarded_exactly(self):
        self.run_helper()
        kwargs = self.m_run_live.call_args.kwargs
        self.assertEqual(kwargs["blog_feeds"], LIVE_KWARGS["blog_feeds"])
        self.assertEqual(kwargs["docs_feeds"], LIVE_KWARGS["docs_feeds"])
        self.assertEqual(
            kwargs["trusted_primary_domains"], LIVE_KWARGS["trusted_primary_domains"]
        )

    def test_run_select_stage_called_once_on_exact_result(self):
        self.run_helper()
        self.m_select.assert_called_once_with(RESEARCH_RESULT)

    def test_selected_candidate_passed_by_identity_to_bridge(self):
        self.run_helper()
        self.assertIs(self.m_bridge.call_args.args[0], SELECTED_CANDIDATE)

    def test_bridge_receives_exact_now(self):
        self.run_helper()
        self.assertIs(self.m_bridge.call_args.kwargs["now"], NOW)

    def test_bridge_result_returned_unchanged(self):
        result = self.run_helper()
        self.assertEqual(result.news_item, NEWS_ITEM)
        self.assertIs(result.selected_candidate, SELECTED_CANDIDATE)
        self.assertIs(result.used_fallback, False)

    def test_successful_path_does_not_call_fallback(self):
        self.run_helper()
        self.m_fallback.assert_not_called()

    def test_bridge_called_exactly_once_on_selected_path(self):
        self.run_helper()
        self.m_bridge.assert_called_once()

    def test_success_log_called(self):
        self.run_helper()
        logged = " ".join(str(c.args[0]) for c in self.log.success.call_args_list)
        self.assertIn("Researcher 2.0:", logged)


class TestNonePath(_Harness):
    def setUp(self):
        super().setUp()
        self.m_select.return_value = None

    def test_bridge_not_called(self):
        self.run_helper()
        self.m_bridge.assert_not_called()

    def test_fallback_called_once(self):
        self.run_helper()
        self.m_fallback.assert_called_once()

    def test_fallback_result_returned_unchanged(self):
        result = self.run_helper()
        self.assertEqual(result.news_item, FALLBACK_ITEM)
        self.assertIsNone(result.selected_candidate)
        self.assertIs(result.used_fallback, True)

    def test_warning_log_called(self):
        self.run_helper()
        logged = " ".join(str(c.args[0]) for c in self.log.warning.call_args_list)
        self.assertIn("не вернул подходящих кандидатов", logged)

    def test_fallback_success_log_called(self):
        self.run_helper()
        logged = " ".join(str(c.args[0]) for c in self.log.success.call_args_list)
        self.assertIn("Fallback тема:", logged)


class TestExceptionFallbackPaths(_Harness):
    def _assert_fallback_path(self):
        result = self.run_helper()
        self.m_fallback.assert_called_once()
        self.assertEqual(result.news_item, FALLBACK_ITEM)
        self.assertIsNone(result.selected_candidate)
        self.assertIs(result.used_fallback, True)
        logged = " ".join(str(c.args[0]) for c in self.log.warning.call_args_list)
        self.assertIn("Ошибка Researcher 2.0", logged)
        return result

    def test_config_exception_fallback_called(self):
        self.m_config.get_research_config.side_effect = RuntimeError("cfg boom")
        self._assert_fallback_path()

    def test_run_live_research_exception_fallback_called(self):
        self.m_run_live.side_effect = RuntimeError("research boom")
        self._assert_fallback_path()

    def test_run_select_stage_exception_fallback_called(self):
        self.m_select.side_effect = ValueError("duplicate processed candidate_id")
        self._assert_fallback_path()

    def test_bridge_exception_fallback_called(self):
        self.m_bridge.side_effect = ValueError("strategic selection is not selected")
        self._assert_fallback_path()

    def test_researcher_path_exception_does_not_propagate(self):
        self.m_run_live.side_effect = RuntimeError("research boom")
        try:
            self.run_helper()
        except Exception:  # pragma: no cover - assertion guard
            self.fail("Researcher-path exception must not propagate")
        self.m_fallback.assert_called_once()

    def test_fallback_exception_propagates(self):
        self.m_select.return_value = None
        self.m_fallback.side_effect = RuntimeError("fallback boom")
        with self.assertRaisesRegex(RuntimeError, "fallback boom"):
            self.run_helper()

    def test_fallback_exception_not_swallowed_after_research_error(self):
        self.m_run_live.side_effect = RuntimeError("research boom")
        self.m_fallback.side_effect = RuntimeError("fallback boom")
        with self.assertRaisesRegex(RuntimeError, "fallback boom"):
            self.run_helper()

    def test_run_select_stage_not_called_if_run_live_research_raises(self):
        self.m_run_live.side_effect = RuntimeError("research boom")
        self.run_helper()
        self.m_select.assert_not_called()

    def test_bridge_not_called_if_run_select_stage_raises(self):
        self.m_select.side_effect = RuntimeError("select boom")
        self.run_helper()
        self.m_bridge.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees (docstring-immune, focused checks only).
# ──────────────────────────────────────────────────────────────────────

def _stripped_tree():
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and \
                    isinstance(node.body[0].value, ast.Constant) and \
                    isinstance(node.body[0].value.value, str):
                node.body = node.body[1:]
    return tree


def _call_names(fn):
    return [
        node.func.id for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]


class TestStructuralBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _stripped_tree()

    def _function(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        raise AssertionError(f"{name} not found")

    def test_main_no_longer_imports_research_result_to_news_item(self):
        self.assertNotIn(
            "research_result_to_news_item", ast.unparse(self.tree)
        )

    def test_main_imports_new_production_boundary(self):
        imported = {
            alias.name
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertIn("run_select_stage", imported)
        self.assertIn("content_candidate_to_news_item", imported)
        self.assertIn("run_live_research", imported)

    def test_helper_does_not_call_old_bridge(self):
        fn = self._function("_get_production_discovery")
        self.assertNotIn("research_result_to_news_item", _call_names(fn))

    def test_exactly_one_call_to_run_select_stage(self):
        fn = self._function("_get_production_discovery")
        calls = [name for name in _call_names(fn) if name == "run_select_stage"]
        self.assertEqual(calls, ["run_select_stage"])

    def test_exactly_one_call_to_content_candidate_to_news_item(self):
        fn = self._function("_get_production_discovery")
        calls = [
            name for name in _call_names(fn)
            if name == "content_candidate_to_news_item"
        ]
        self.assertEqual(calls, ["content_candidate_to_news_item"])

    def test_no_lower_level_select_imports_or_calls(self):
        text = ast.unparse(self.tree)
        forbidden = (
            "select_research_result_winner", "select_shortlist_winner",
            "select_ranked_candidate", "build_selected_content_candidate",
            "RankedCandidate", "RankingResult", "ContentCandidate",
            "CandidateStage",
        )
        for token in forbidden:
            self.assertNotIn(token, text)

    def test_fallback_call_remains_outside_try_body(self):
        fn = self._function("_get_production_discovery")
        try_node = next(
            node for node in ast.walk(fn) if isinstance(node, ast.Try)
        )
        inside_try = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "get_fallback_topic"
            for node in ast.walk(
                ast.Module(body=try_node.body, type_ignores=[])
            )
        )
        total = _call_names(fn).count("get_fallback_topic")
        self.assertEqual(total, 1)
        self.assertFalse(inside_try)

    def test_unrelated_code_not_modified_semantically(self):
        # Focused checks: research imports, Step 0 seam, and pipeline
        # imports are all still exactly as before this step.
        research_modules = {
            node.module
            for node in self.tree.body
            if isinstance(node, ast.ImportFrom) and node.module
            and node.module.startswith("src.research")
        }
        self.assertEqual(
            research_modules,
            {"src.research.live", "src.research.select_stage", "src.research.legacy_bridge"},
        )

        inner = self._function("_run_pipeline_inner")
        discovery_calls = [
            name for name in _call_names(inner)
            if name == "_get_production_discovery"
        ]
        self.assertEqual(discovery_calls, ["_get_production_discovery"])
        self.assertNotIn("_get_production_news_item", _call_names(inner))
        for forbidden_call in (
            "run_select_stage", "content_candidate_to_news_item",
            "research_result_to_news_item", "get_fallback_topic",
            "run_live_research",
        ):
            self.assertNotIn(forbidden_call, _call_names(inner))

        imported = {
            alias.name
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        for required in (
            "get_fallback_topic", "create_content_plan", "write_post",
            "edit_post", "create_image_for_post", "publish_post",
            "log_publication", "print_report", "validate_content_plan",
            "StateService",
        ):
            self.assertIn(required, imported)


if __name__ == "__main__":
    unittest.main()
