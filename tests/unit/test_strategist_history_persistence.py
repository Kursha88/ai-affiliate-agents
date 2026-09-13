"""Step 13H-A: Strategist side-effect-free mode (persist_history flag).

Proves that ``create_content_plan``:
  - persists history by default (production behavior unchanged);
  - performs ZERO persistence when ``persist_history=False`` while still
    returning the identical valid plan;
  - forwards the flag through the affiliate-mode recursive fallback.

All filesystem-touching internals are patched: no real files are read or
written. ``MODE`` is patched to ``"growth"`` so the affiliate branch (and its
recursion) stays structural-only (AST test).
"""

import ast
import unittest
from pathlib import Path
from unittest import mock

from src.agents import strategist

STRATEGIST_PATH = Path(__file__).resolve().parents[2] / "src" / "agents" / "strategist.py"

NEWS = {
    "title": "Research Candidate",
    "source": "github",
    "url": "https://example.com/item",
    "age_hours": 2.0,
}

SETTINGS = {
    "content": {
        "formats": ["Case"],
        "topics": ["Fallback"],
    }
}


class _PatchedStrategist(unittest.TestCase):
    """Shared patch harness: MODE=growth + all I/O boundaries mocked."""

    def setUp(self):
        self.history = []
        self.m_load_yaml = mock.patch.object(
            strategist, "_load_yaml", return_value=SETTINGS
        ).start()
        self.m_load_json = mock.patch.object(
            strategist, "_load_json", return_value=self.history
        ).start()
        self.m_get_unused_format = mock.patch.object(
            strategist, "_get_unused_format", return_value="Case"
        ).start()
        self.m_get_channel_link = mock.patch.object(
            strategist, "_get_channel_link", return_value="https://t.me/test"
        ).start()
        self.m_save_json = mock.patch.object(strategist, "_save_json").start()
        self.m_mode = mock.patch.object(strategist, "MODE", "growth").start()
        # Strategist legitimately prints emoji/Cyrillic progress lines; the test
        # runner's console is cp1251, so silence print() during exercise.
        mock.patch("builtins.print").start()
        self.addCleanup(mock.patch.stopall)


class TestDefaultPersistence(_PatchedStrategist):
    """Tests 1-4: default and explicit persist_history=True persist."""

    def test_default_call_saves_history_exactly_once(self):
        plan = strategist.create_content_plan(news_item=dict(NEWS))
        self.assertIsInstance(plan, dict)
        self.m_save_json.assert_called_once()

    def test_default_call_writes_to_exact_topic_history_path(self):
        strategist.create_content_plan(news_item=dict(NEWS))
        (path, _data), _kwargs = self.m_save_json.call_args
        self.assertEqual(path, "data/topic_history.json")
        self.assertEqual(self.m_save_json.call_args.kwargs, {})

    def test_default_persisted_history_has_exactly_one_appended_record(self):
        strategist.create_content_plan(news_item=dict(NEWS))
        (_path, data), _kwargs = self.m_save_json.call_args
        self.assertEqual(len(data), 1)
        record = data[0]
        self.assertEqual(record["topic"], "Research Candidate")
        self.assertEqual(record["format"], "Case")
        self.assertEqual(record["product"], "channel")
        self.assertEqual(record["mode"], "growth")
        self.assertIsInstance(record["date"], str)
        self.assertTrue(record["date"])

    def test_explicit_persist_history_true_behaves_same(self):
        strategist.create_content_plan(news_item=dict(NEWS), persist_history=True)
        self.m_save_json.assert_called_once()


class TestNoPersistence(_PatchedStrategist):
    """Tests 5-11: persist_history=False is fully side-effect free."""

    def test_persist_history_false_never_saves(self):
        strategist.create_content_plan(news_item=dict(NEWS), persist_history=False)
        self.m_save_json.assert_not_called()

    def test_persist_history_false_does_not_mutate_history_list(self):
        sentinel = []
        self.m_load_json.return_value = sentinel
        strategist.create_content_plan(news_item=dict(NEWS), persist_history=False)
        self.assertEqual(sentinel, [])

    def test_persist_history_false_still_returns_valid_plan_dict(self):
        plan = strategist.create_content_plan(news_item=dict(NEWS), persist_history=False)
        self.assertIsInstance(plan, dict)
        self.assertEqual(plan["mode"], "growth")
        self.assertEqual(plan["format"], "Case")

    def test_persist_history_false_plan_topic(self):
        plan = strategist.create_content_plan(news_item=dict(NEWS), persist_history=False)
        self.assertEqual(plan["topic"], "Research Candidate")

    def test_persist_history_false_plan_news_source(self):
        plan = strategist.create_content_plan(news_item=dict(NEWS), persist_history=False)
        self.assertEqual(plan["news"]["source"], "github")

    def test_persist_history_false_plan_news_url(self):
        plan = strategist.create_content_plan(news_item=dict(NEWS), persist_history=False)
        self.assertEqual(plan["news"]["url"], "https://example.com/item")

    def test_persist_history_false_plan_news_age_hours(self):
        plan = strategist.create_content_plan(news_item=dict(NEWS), persist_history=False)
        self.assertEqual(plan["news"]["age_hours"], 2.0)


def _load_plan_function():
    tree = ast.parse(STRATEGIST_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "create_content_plan":
            return node
    raise AssertionError("create_content_plan not found at module level")


def _call_name(func_node):
    if isinstance(func_node, ast.Name):
        return func_node.id
    if isinstance(func_node, ast.Attribute):
        return func_node.attr
    return None


def _save_json_calls_outside_persist_guard(fn):
    """Return Call nodes to _save_json that are NOT inside `if persist_history:`."""
    found = []

    def walk(node, inside_guard):
        if isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Name) and test.id == "persist_history":
                inside_guard = True
        if (
            isinstance(node, ast.Call)
            and _call_name(node.func) == "_save_json"
            and not inside_guard
        ):
            found.append(node)
        for child in ast.iter_child_nodes(node):
            walk(child, inside_guard)

    walk(fn, False)
    return found


class TestStructuralBoundaries(unittest.TestCase):
    """Tests 12-14: AST-level guarantees on the new flag wiring."""

    @classmethod
    def setUpClass(cls):
        cls.fn = _load_plan_function()

    def test_persist_history_is_keyword_only_with_default_true(self):
        kw_names = [a.arg for a in self.fn.args.kwonlyargs]
        self.assertIn("persist_history", kw_names)
        idx = kw_names.index("persist_history")
        default = self.fn.args.kw_defaults[idx]
        self.assertIsInstance(default, ast.Constant)
        self.assertIs(default.value, True)
        # news_item stays a regular positional-or-keyword parameter.
        self.assertIn("news_item", [a.arg for a in self.fn.args.args])

    def test_save_json_call_exists_only_inside_persist_guard(self):
        all_save_calls = [
            node
            for node in ast.walk(self.fn)
            if isinstance(node, ast.Call) and _call_name(node.func) == "_save_json"
        ]
        self.assertEqual(len(all_save_calls), 1)
        outside = _save_json_calls_outside_persist_guard(self.fn)
        self.assertEqual(outside, [])

    def test_recursive_call_forwards_persist_history(self):
        recursive = [
            node
            for node in ast.walk(self.fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "create_content_plan"
        ]
        self.assertTrue(recursive, "expected the affiliate-mode recursive call")
        for call in recursive:
            keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
            self.assertIn("persist_history", keywords)
            value = keywords["persist_history"]
            self.assertIsInstance(value, ast.Name)
            self.assertEqual(value.id, "persist_history")


if __name__ == "__main__":
    unittest.main()
