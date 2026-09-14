"""Step 14G unit tests: production dry run on the SELECT-stage path.

Patches all collaborators at the point of use in
``src.research.production_dry_run`` with identity sentinels so forwarding
behavior is proven independently. Structural AST tests bind the
orchestration-only and display-only boundaries to actual code.
"""

import ast
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from src.research import production_dry_run as pdr
from src.research.production_dry_run import (
    ProductionDryRunResult,
    format_production_dry_run,
    run_production_dry_run,
)

SOURCE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "research" / "production_dry_run.py"
)

NOW = object()
RESEARCH_RESULT = object()
SELECTED_CANDIDATE = object()
NEWS_ITEM = {"title": "Selected Winner", "source": "github",
             "url": "https://example.com/winner", "age_hours": 1.5}
PLAN = {"topic": "T", "format": "Case", "mode": "growth", "platform": "telegram"}
VALIDATION = {"valid": True, "issues": []}
LIVE_KWARGS = {
    "blog_feeds": ("blog",),
    "docs_feeds": ("docs",),
    "trusted_primary_domains": ("example.com",),
}


class _Harness(unittest.TestCase):
    """Patch every collaborator where it is USED (production_dry_run module)."""

    def setUp(self):
        self.config = mock.Mock()
        self.config.live_kwargs.return_value = dict(LIVE_KWARGS)
        self.m_config = mock.patch.object(pdr, "Config").start()
        self.m_config.get_research_config.return_value = self.config
        self.m_run_live = mock.patch.object(
            pdr, "run_live_research", return_value=RESEARCH_RESULT
        ).start()
        self.m_select = mock.patch.object(
            pdr, "run_select_stage", return_value=SELECTED_CANDIDATE
        ).start()
        self.m_bridge = mock.patch.object(
            pdr, "content_candidate_to_news_item", return_value=dict(NEWS_ITEM)
        ).start()
        self.m_create = mock.patch.object(
            pdr, "create_content_plan", return_value=self.plan_sentinel()
        ).start()
        self.m_validate = mock.patch.object(
            pdr, "validate_content_plan", return_value=dict(VALIDATION)
        ).start()
        self.addCleanup(mock.patch.stopall)

    def plan_sentinel(self):
        return {"topic": "T", "format": "Case", "mode": "growth", "platform": "telegram"}

    def run_dry(self, **kwargs):
        return run_production_dry_run(now=NOW, **kwargs)


class TestSelectedPath(_Harness):
    def test_config_get_research_config_called_once(self):
        self.run_dry(limit=3)
        self.m_config.get_research_config.assert_called_once()

    def test_run_live_research_called_once(self):
        self.run_dry(limit=3)
        self.m_run_live.assert_called_once()

    def test_run_live_research_gets_exact_now(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_run_live.call_args.kwargs["now"], NOW)

    def test_run_live_research_gets_provided_limit(self):
        self.run_dry(limit=7)
        self.assertEqual(self.m_run_live.call_args.kwargs["limit"], 7)

    def test_live_kwargs_forwarded_exactly(self):
        self.run_dry(limit=3)
        kwargs = self.m_run_live.call_args.kwargs
        self.assertEqual(kwargs["blog_feeds"], LIVE_KWARGS["blog_feeds"])
        self.assertEqual(kwargs["docs_feeds"], LIVE_KWARGS["docs_feeds"])
        self.assertEqual(
            kwargs["trusted_primary_domains"], LIVE_KWARGS["trusted_primary_domains"]
        )

    def test_run_select_stage_called_once_with_exact_research_result(self):
        self.run_dry(limit=3)
        self.m_select.assert_called_once_with(RESEARCH_RESULT)

    def test_selected_candidate_preserved_by_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.selected_candidate, SELECTED_CANDIDATE)

    def test_bridge_receives_exact_selected_candidate(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_bridge.call_args.args[0], SELECTED_CANDIDATE)

    def test_bridge_receives_exact_now(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_bridge.call_args.kwargs["now"], NOW)

    def test_news_item_preserved_by_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.news_item, self.m_bridge.return_value)

    def test_strategist_receives_exact_news_item(self):
        result = self.run_dry(limit=3)
        self.assertIs(self.m_create.call_args.kwargs["news_item"], result.news_item)

    def test_strategist_called_with_persist_history_false(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_create.call_args.kwargs["persist_history"], False)

    def test_plan_preserved_by_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.plan, self.m_create.return_value)

    def test_validator_receives_exact_plan(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_validate.call_args.args[0], self.m_create.return_value)

    def test_validation_preserved_by_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.validation, self.m_validate.return_value)

    def test_used_fallback_is_false(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.used_fallback, False)

    def test_stop_reason_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.stop_reason)

    def test_research_result_preserved_by_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.research_result, RESEARCH_RESULT)


class TestNoSelectedCandidatePath(_Harness):
    def setUp(self):
        super().setUp()
        self.m_select.return_value = None

    def test_selected_candidate_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.selected_candidate)

    def test_news_item_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.news_item)

    def test_plan_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.plan)

    def test_validation_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.validation)

    def test_used_fallback_is_false(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.used_fallback, False)

    def test_stop_reason_is_no_selected_candidate(self):
        result = self.run_dry(limit=3)
        self.assertEqual(result.stop_reason, "no_selected_candidate")

    def test_bridge_not_called(self):
        self.run_dry(limit=3)
        self.m_bridge.assert_not_called()

    def test_strategist_not_called(self):
        self.run_dry(limit=3)
        self.m_create.assert_not_called()

    def test_validator_not_called(self):
        self.run_dry(limit=3)
        self.m_validate.assert_not_called()


class TestExceptionPropagation(_Harness):
    def test_config_exception_propagates(self):
        self.m_config.get_research_config.side_effect = RuntimeError("cfg boom")
        with self.assertRaisesRegex(RuntimeError, "cfg boom"):
            self.run_dry(limit=3)

    def test_run_live_research_exception_propagates(self):
        self.m_run_live.side_effect = RuntimeError("research boom")
        with self.assertRaisesRegex(RuntimeError, "research boom"):
            self.run_dry(limit=3)

    def test_run_select_stage_exception_propagates(self):
        self.m_select.side_effect = ValueError("duplicate processed candidate_id")
        with self.assertRaisesRegex(ValueError, "duplicate processed candidate_id"):
            self.run_dry(limit=3)

    def test_bridge_exception_propagates(self):
        self.m_bridge.side_effect = ValueError("strategic selection is not selected")
        with self.assertRaisesRegex(ValueError, "strategic selection is not selected"):
            self.run_dry(limit=3)

    def test_strategist_exception_propagates(self):
        self.m_create.side_effect = RuntimeError("strategist boom")
        with self.assertRaisesRegex(RuntimeError, "strategist boom"):
            self.run_dry(limit=3)

    def test_validator_exception_propagates(self):
        self.m_validate.side_effect = RuntimeError("validator boom")
        with self.assertRaisesRegex(RuntimeError, "validator boom"):
            self.run_dry(limit=3)

    def test_no_fallback_function_called_or_imported(self):
        # get_fallback_topic must not exist anywhere in the module.
        self.assertFalse(hasattr(pdr, "get_fallback_topic"))
        source = SOURCE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("get_fallback_topic", source)


class _FakeCluster:
    value = "vibe_coding"


class _FakeFormat:
    value = "practical_guide"


class _FakeSelection:
    recommended_format = _FakeFormat()
    research_required = False
    experiment_required = True


class _FakeCandidate:
    title = "VibeWorks CLI"
    content_cluster = _FakeCluster()


class _FakeSelected:
    """Fresh per-instance selection so class-level mutation cannot leak."""

    def __init__(self):
        self.candidate = _FakeCandidate()
        self.selection = _FakeSelection()


class _FakeRanked:
    ranked = tuple(object() for _ in range(8))


class _FakeResearch:
    input_count = 11
    deduplicated_count = 10
    classified_count = 10
    verified_count = 10
    scored_count = 10

    def __init__(self):
        self.ranked = _FakeRanked()


class _FakeResult:
    def __init__(self, selected):
        self.research_result = _FakeResearch()
        self.selected_candidate = _FakeSelected() if selected else None
        # news_item is a real legacy dict (mirrors content_candidate_to_news_item).
        self.news_item = (
            {"title": "VibeWorks CLI", "source": "github",
             "url": "https://github.com/vibeworks/cli", "age_hours": 0.27}
            if selected else None
        )
        self.plan = {"topic": "T", "format": "Case", "mode": "growth",
                     "platform": "telegram"} if selected else None
        self.validation = {"valid": True, "issues": []} if selected else None
        self.used_fallback = False
        self.stop_reason = None if selected else "no_selected_candidate"


class TestFormatter(unittest.TestCase):
    def test_header_contains_select(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        self.assertIn("Researcher 2.0 -> SELECT -> Strategist LIVE dry run", text)

    def test_selected_section_uses_selected_candidate_data(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        self.assertIn("title=VibeWorks CLI", text)
        self.assertIn("cluster=vibe_coding", text)
        self.assertIn("format=practical_guide", text)
        self.assertIn("research_required=False", text)
        self.assertIn("experiment_required=True", text)

    def test_formatter_reports_cluster(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        self.assertIn("cluster=vibe_coding", text)

    def test_formatter_reports_recommended_format(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        self.assertIn("format=practical_guide", text)

    def test_formatter_reports_research_required(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        self.assertIn("research_required=False", text)

    def test_formatter_reports_experiment_required(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        self.assertIn("experiment_required=True", text)

    def test_recommended_format_none_renders_empty(self):
        fake = _FakeResult(selected=True)
        fake.selected_candidate.selection.recommended_format = None
        text = format_production_dry_run(fake)
        self.assertIn("format=", text)

    def test_legacy_news_item_section_separate(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        self.assertIn("Legacy news_item:", text)
        self.assertIn("source=github", text)
        self.assertIn("url=https://github.com/vibeworks/cli", text)
        self.assertIn("age_hours=0.27", text)

    def test_empty_when_no_selected_candidate(self):
        text = format_production_dry_run(_FakeResult(selected=False))
        self.assertIn("(empty)", text)
        self.assertIn("stop_reason=no_selected_candidate", text)

    def test_stop_reason_printed_when_present(self):
        text = format_production_dry_run(_FakeResult(selected=False))
        self.assertIn("stop_reason=no_selected_candidate", text)

    def test_formatter_does_not_call_run_select_stage(self):
        with mock.patch.object(pdr, "run_select_stage") as m_select:
            format_production_dry_run(_FakeResult(selected=True))
            m_select.assert_not_called()

    def test_formatter_does_not_mutate_result(self):
        fake = _FakeResult(selected=True)
        snapshot_selected = fake.selected_candidate
        snapshot_news = fake.news_item
        format_production_dry_run(fake)
        self.assertIs(fake.selected_candidate, snapshot_selected)
        self.assertIs(fake.news_item, snapshot_news)


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

    def _function(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        raise AssertionError(f"{name} not found")

    def test_no_research_result_to_news_item_reference(self):
        self.assertNotIn("research_result_to_news_item", self.text)

    def test_exactly_one_run_select_stage_call(self):
        fn = self._function("run_production_dry_run")
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "run_select_stage"
        ]
        self.assertEqual(len(calls), 1)

    def test_exactly_one_content_candidate_to_news_item_call(self):
        fn = self._function("run_production_dry_run")
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "content_candidate_to_news_item"
        ]
        self.assertEqual(len(calls), 1)

    def test_no_lower_level_select_imports_or_calls(self):
        forbidden = (
            "select_research_result_winner", "select_shortlist_winner",
            "select_ranked_candidate", "build_selected_content_candidate",
        )
        for token in forbidden:
            self.assertNotIn(token, self.text)

    def test_no_state_db_publisher_integrations(self):
        forbidden = (
            "StateService", "sqlite3", "publisher", "Publisher",
            "copywriter", "Copywriter", "editor", "Editor",
            "designer", "Designer", "telegram", "Telegram",
            "x_client", "vk_client", "pinterest_client",
            "ContentItem", "Publication",
        )
        for token in forbidden:
            self.assertNotIn(token, self.text)

    def test_new_dataclass_field_order(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == "ProductionDryRunResult":
                fields = [
                    stmt.target.id for stmt in node.body
                    if isinstance(stmt, ast.AnnAssign)
                ]
                self.assertEqual(
                    fields,
                    ["research_result", "selected_candidate", "news_item",
                     "plan", "validation", "used_fallback", "stop_reason"],
                )
                return
        self.fail("ProductionDryRunResult not found")

    def test_stop_reason_literal(self):
        fn = self._function("run_production_dry_run")
        literals = [
            node.value.value for node in ast.walk(fn)
            if isinstance(node, ast.keyword) and node.arg == "stop_reason"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ]
        self.assertEqual(literals, ["no_selected_candidate"])


if __name__ == "__main__":
    unittest.main()
