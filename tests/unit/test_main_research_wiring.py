"""Unit tests for Researcher 2.0 wiring into production Step 0 (Step 13G)."""

import ast
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import src.main as main_module
from src.main import _get_production_news_item

PROJECT_ROOT = Path(__file__).resolve().parents[2]

NOW = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)

LIVE_KWARGS = {
    "blog_feeds": ("blog",),
    "docs_feeds": ("docs",),
    "trusted_primary_domains": ("example.com",),
}

NEWS_ITEM = {
    "title": "Test Research Candidate",
    "source": "github",
    "url": "https://example.com/item",
    "age_hours": 2.5,
}

FALLBACK_ITEM = {
    "title": "Fallback Topic",
    "source": "editorial",
    "url": "",
    "age_hours": 0,
}


def _fake_config(live_kwargs_result=None):
    return SimpleNamespace(
        live_kwargs=MagicMock(return_value=dict(live_kwargs_result or LIVE_KWARGS))
    )


class _WiringTestCase(unittest.TestCase):
    """Shared patching: all dependencies patched where they are USED (src.main)."""

    def setUp(self):
        self.config_patcher = patch("src.main.Config")
        self.research_patcher = patch("src.main.run_live_research")
        self.bridge_patcher = patch("src.main.research_result_to_news_item")
        self.fallback_patcher = patch("src.main.get_fallback_topic")

        self.config_m = self.config_patcher.start()
        self.research_m = self.research_patcher.start()
        self.bridge_m = self.bridge_patcher.start()
        self.fallback_m = self.fallback_patcher.start()
        for patcher in (
            self.config_patcher,
            self.research_patcher,
            self.bridge_patcher,
            self.fallback_patcher,
        ):
            self.addCleanup(patcher.stop)

        self.fake_config = _fake_config()
        self.config_m.get_research_config.return_value = self.fake_config
        self.fake_result = object()  # plain fake ResearchResult
        self.research_m.return_value = self.fake_result
        self.bridge_m.return_value = dict(NEWS_ITEM)
        self.fallback_m.return_value = dict(FALLBACK_ITEM)

        self.log = MagicMock()

    def run_helper(self, now=NOW):
        return _get_production_news_item(now=now, log=self.log)


class TestSuccessfulResearchPath(_WiringTestCase):
    def test_config_get_research_config_called_once(self):
        self.run_helper()
        self.config_m.get_research_config.assert_called_once_with()

    def test_live_kwargs_called_once(self):
        self.run_helper()
        self.fake_config.live_kwargs.assert_called_once_with()

    def test_run_live_research_called_once(self):
        self.run_helper()
        self.research_m.assert_called_once()

    def test_run_live_research_receives_injected_now(self):
        self.run_helper()
        self.assertEqual(self.research_m.call_args.kwargs["now"], NOW)

    def test_run_live_research_receives_limit_5(self):
        self.run_helper()
        self.assertEqual(self.research_m.call_args.kwargs["limit"], 5)

    def test_live_kwargs_forwarded_exactly(self):
        self.run_helper()
        kwargs = self.research_m.call_args.kwargs
        self.assertEqual(
            kwargs["blog_feeds"], ("blog",)
        )
        self.assertEqual(kwargs["docs_feeds"], ("docs",))
        self.assertEqual(
            kwargs["trusted_primary_domains"], ("example.com",)
        )
        self.assertEqual(
            set(kwargs),
            {"now", "limit", "blog_feeds", "docs_feeds", "trusted_primary_domains"},
        )

    def test_bridge_called_once(self):
        self.run_helper()
        self.bridge_m.assert_called_once()

    def test_bridge_receives_exact_research_result(self):
        self.run_helper()
        self.assertIs(self.bridge_m.call_args.args[0], self.fake_result)

    def test_bridge_receives_injected_now(self):
        self.run_helper()
        self.assertEqual(self.bridge_m.call_args.kwargs["now"], NOW)

    def test_news_item_returned_unchanged_by_identity(self):
        expected = {"title": "X", "source": "s", "url": "u", "age_hours": 1.0}
        self.bridge_m.return_value = expected
        item = self.run_helper()
        self.assertIs(item, expected)

    def test_success_path_does_not_call_fallback(self):
        self.run_helper()
        self.fallback_m.assert_not_called()

    def test_success_path_logs_researcher_success(self):
        self.run_helper()
        success_texts = " ".join(
            str(call.args[0]) for call in self.log.success.call_args_list
        )
        self.assertIn("Researcher 2.0:", success_texts)


class TestEmptyResultFallbackPath(_WiringTestCase):
    def setUp(self):
        super().setUp()
        self.bridge_m.return_value = None

    def test_fallback_called_exactly_once(self):
        self.run_helper()
        self.fallback_m.assert_called_once_with()

    def test_fallback_returned_unchanged_by_identity(self):
        fallback = {"title": "F", "source": "editorial", "url": "", "age_hours": 0}
        self.fallback_m.return_value = fallback
        item = self.run_helper()
        self.assertIs(item, fallback)

    def test_empty_result_logs_warning(self):
        self.run_helper()
        warning_texts = " ".join(
            str(call.args[0]) for call in self.log.warning.call_args_list
        )
        self.assertIn(
            "Researcher 2.0 не вернул подходящих кандидатов", warning_texts
        )

    def test_fallback_path_logs_fallback_success(self):
        self.run_helper()
        success_texts = " ".join(
            str(call.args[0]) for call in self.log.success.call_args_list
        )
        self.assertIn("Fallback тема:", success_texts)


class TestExceptionFallbackPaths(_WiringTestCase):
    def test_config_error_uses_fallback_once(self):
        self.config_m.get_research_config.side_effect = RuntimeError("config boom")
        item = self.run_helper()
        self.fallback_m.assert_called_once_with()
        self.assertEqual(item, FALLBACK_ITEM)

    def test_run_live_research_error_uses_fallback_once(self):
        self.research_m.side_effect = RuntimeError("network boom")
        item = self.run_helper()
        self.fallback_m.assert_called_once_with()
        self.assertEqual(item, FALLBACK_ITEM)

    def test_bridge_error_uses_fallback_once(self):
        self.bridge_m.side_effect = ValueError("bridge boom")
        item = self.run_helper()
        self.fallback_m.assert_called_once_with()
        self.assertEqual(item, FALLBACK_ITEM)

    def test_researcher_exception_logs_warning(self):
        self.research_m.side_effect = RuntimeError("network boom")
        self.run_helper()
        warning_texts = " ".join(
            str(call.args[0]) for call in self.log.warning.call_args_list
        )
        self.assertIn("Ошибка Researcher 2.0", warning_texts)

    def test_fallback_own_error_propagates_from_empty_result_path(self):
        self.bridge_m.return_value = None
        self.fallback_m.side_effect = RuntimeError("fallback boom")
        with self.assertRaises(RuntimeError):
            self.run_helper()

    def test_fallback_own_error_propagates_from_exception_path(self):
        self.research_m.side_effect = RuntimeError("network boom")
        self.fallback_m.side_effect = RuntimeError("fallback boom")
        with self.assertRaises(RuntimeError):
            self.run_helper()


class TestStructuralBoundaries(unittest.TestCase):
    """AST guarantees binding actual code (docstrings/comments excluded by AST)."""

    @classmethod
    def setUpClass(cls):
        cls.source = (PROJECT_ROOT / "src" / "main.py").read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(cls.source)
        cls.functions = {
            node.name: node
            for node in cls.tree.body
            if isinstance(node, ast.FunctionDef)
        }

    def _call_descriptors(self, function_node):
        descriptors = []
        for node in ast.walk(function_node):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    descriptors.append(("name", func.id))
                elif isinstance(func, ast.Attribute):
                    root = (
                        func.value.id
                        if isinstance(func.value, ast.Name)
                        else ast.dump(func.value)
                    )
                    descriptors.append(("attr", f"{root}.{func.attr}"))
        return descriptors

    def test_helper_has_no_clock_random_hunter_or_pipeline_calls(self):
        helper = self.functions["_get_production_news_item"]
        descriptors = self._call_descriptors(helper)

        banned_exact = {
            ("name", "get_top_ai_news"),
            ("name", "random"),
            ("attr", "random.random"),
            ("attr", "datetime.now"),
            ("attr", "datetime.utcnow"),
            # DB / state / publishing boundaries:
            ("name", "publish_post"),
            ("name", "log_publication"),
            ("name", "StateService"),
            ("name", "open"),
            ("attr", "state.begin_publication"),
            ("attr", "state.mark_publication_published"),
            ("attr", "state.fail_run"),
            ("attr", "state.complete_run"),
        }
        for descriptor in descriptors:
            self.assertNotIn(descriptor, banned_exact)

        # clock: no attribute call named now/utcnow at all
        for kind, text in descriptors:
            if kind == "attr":
                self.assertFalse(
                    text.endswith(".now") or text.endswith(".utcnow"),
                    f"hidden clock call in helper: {text}",
                )

    def test_helper_calls_are_only_expected_ones(self):
        helper = self.functions["_get_production_news_item"]
        descriptors = set(self._call_descriptors(helper))
        allowed = {
            ("attr", "Config.get_research_config"),
            ("name", "run_live_research"),
            ("name", "research_result_to_news_item"),
            ("name", "get_fallback_topic"),
            ("attr", "log.success"),
            ("attr", "log.warning"),
        }
        # live_kwargs root is the local config variable name — accept any *.live_kwargs
        unexpected = {
            d for d in descriptors
            if d not in allowed and not d[1].endswith(".live_kwargs")
        }
        self.assertEqual(
            unexpected,
            set(),
            f"unexpected calls in helper: {sorted(unexpected)}",
        )

    def test_step0_uses_helper_with_utc_clock_and_log(self):
        inner = self.functions["_run_pipeline_inner"]

        step0_calls = [
            node
            for node in ast.walk(inner)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_get_production_news_item"
        ]
        self.assertEqual(len(step0_calls), 1)
        call = step0_calls[0]

        # keyword now=<datetime.now(timezone.utc)>
        self.assertIn("now", [kw.arg for kw in call.keywords])
        now_kw = next(kw for kw in call.keywords if kw.arg == "now")
        self.assertIsInstance(now_kw.value, ast.Call)
        now_call = now_kw.value
        self.assertIsInstance(now_call.func, ast.Attribute)
        self.assertEqual(now_call.func.attr, "now")
        self.assertIsInstance(now_call.func.value, ast.Name)
        self.assertEqual(now_call.func.value.id, "datetime")
        self.assertEqual(len(now_call.args), 1)
        utc_arg = now_call.args[0]
        self.assertIsInstance(utc_arg, ast.Attribute)
        self.assertEqual(utc_arg.attr, "utc")
        self.assertIsInstance(utc_arg.value, ast.Name)
        self.assertEqual(utc_arg.value.id, "timezone")

        # keyword log=log
        log_kw = next(kw for kw in call.keywords if kw.arg == "log")
        self.assertIsInstance(log_kw.value, ast.Name)
        self.assertEqual(log_kw.value.id, "log")

    def test_no_production_get_top_ai_news_call_anywhere(self):
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "get_top_ai_news"
            ):
                self.fail("get_top_ai_news(...) is still called in src/main.py")

        # and the name is not even imported anymore (it became unused)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module == (
                "src.agents.news_hunter"
            ):
                imported = {alias.name for alias in node.names}
                self.assertNotIn("get_top_ai_news", imported)
                self.assertIn("get_fallback_topic", imported)

    def test_no_random_in_pipeline_inner(self):
        inner = self.functions["_run_pipeline_inner"]
        for node in ast.walk(inner):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "random")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "random"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "random"
            ):
                self.fail("random.random() still used inside _run_pipeline_inner")


if __name__ == "__main__":
    unittest.main()
