"""Step 15H-A unit tests: production dry run on the Strategist 2.0 select path.

Patches all collaborators at the point of use in
``src.research.production_dry_run`` with identity sentinels so forwarding
behavior is proven independently. A real tz-aware datetime and a real
StrategistPlan fixture are used because the runner now formats timestamps and
carries the plan through the legacy bridge. Structural AST tests bind the
orchestration-only and display-only boundaries to actual code.
"""

import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from src.domain.strategy import ContentCluster, ContentFormat, TargetPlatform
from src.domain.strategist import StrategistPlan
from src.research import production_dry_run as pdr
from src.research.production_dry_run import (
    ProductionDryRunResult,
    format_production_dry_run,
    run_production_dry_run,
)

SOURCE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "research" / "production_dry_run.py"
)

NOW = datetime(2026, 9, 18, 18, 0, 0, tzinfo=timezone.utc)
RESEARCH_RESULT = object()
SELECTED_CANDIDATE = object()
NEWS_ITEM = {"title": "Selected Winner", "source": "github",
             "url": "https://example.com/winner", "age_hours": 1.5}
PLAN_STRUCTURE = ("hook", "prerequisites", "steps", "result", "cta")
PLAN_PLATFORMS = (TargetPlatform.TELEGRAM, TargetPlatform.X)
STRATEGIST_PLAN = StrategistPlan(
    candidate_id="cand-42",
    topic="VibeWorks CLI ships local agents",
    content_cluster=ContentCluster.VIBE_CODING,
    content_format=ContentFormat.PRACTICAL_GUIDE,
    target_platforms=PLAN_PLATFORMS,
    research_required=False,
    experiment_required=True,
    angle="How it changes the practical dev process",
    hook="VibeWorks CLI ships local agents",
    objective="Teach the task step by step",
    cta="Repeat the steps",
    cta_link="https://example.com/winner",
    tone="teaching and practical",
    structure=PLAN_STRUCTURE,
    language="ru",
    mode="growth",
)
PLAN = {
    "created_at": "2026-09-18T18:00:00+00:00",
    "mode": "growth",
    "platform": "telegram",
    "candidate_id": "cand-42",
    "topic": "VibeWorks CLI ships local agents",
    "format": "practical_guide",
    "content_format": "practical_guide",
    "content_cluster": "vibe_coding",
    "target_platforms": ("telegram", "x"),
    "research_required": False,
    "experiment_required": True,
    "angle": "How it changes the practical dev process",
    "hook": "VibeWorks CLI ships local agents",
    "objective": "Teach the task step by step",
    "tone": "teaching and practical",
    "structure": PLAN_STRUCTURE,
    "news": {"source": "github", "url": "https://example.com/winner",
             "age_hours": 1.5},
    "product": {"id": "source"},
    "language": "ru",
    "cta": "Repeat the steps",
    "cta_link": "https://example.com/winner",
    "is_affiliate": False,
}
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
        self.m_news_bridge = mock.patch.object(
            pdr, "content_candidate_to_news_item", return_value=dict(NEWS_ITEM)
        ).start()
        self.m_strategist = mock.patch.object(
            pdr, "run_strategist", return_value=STRATEGIST_PLAN
        ).start()
        self.m_plan_bridge = mock.patch.object(
            pdr, "strategist_plan_to_legacy_plan", return_value=dict(PLAN)
        ).start()
        self.m_validate = mock.patch.object(
            pdr, "validate_content_plan", return_value=dict(VALIDATION)
        ).start()
        self.addCleanup(mock.patch.stopall)

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

    def test_news_bridge_receives_exact_selected_candidate(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_news_bridge.call_args.args[0], SELECTED_CANDIDATE)

    def test_news_bridge_receives_exact_now(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_news_bridge.call_args.kwargs["now"], NOW)

    def test_news_item_preserved_by_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.news_item, self.m_news_bridge.return_value)

    def test_run_strategist_called_exactly_once(self):
        self.run_dry(limit=3)
        self.m_strategist.assert_called_once()

    def test_run_strategist_gets_exact_selected_candidate(self):
        self.run_dry(limit=3)
        self.m_strategist.assert_called_once_with(SELECTED_CANDIDATE)

    def test_strategist_plan_preserved_by_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.strategist_plan, STRATEGIST_PLAN)
        self.assertIs(result.strategist_plan, self.m_strategist.return_value)

    def test_plan_bridge_called_exactly_once(self):
        self.run_dry(limit=3)
        self.m_plan_bridge.assert_called_once()

    def test_plan_bridge_gets_exact_strategist_plan(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_plan_bridge.call_args.args[0], STRATEGIST_PLAN)

    def test_plan_bridge_created_at_is_now_isoformat(self):
        self.run_dry(limit=3)
        self.assertEqual(
            self.m_plan_bridge.call_args.kwargs["created_at"], NOW.isoformat()
        )

    def test_plan_bridge_news_source_from_news_item(self):
        result = self.run_dry(limit=3)
        self.assertEqual(
            self.m_plan_bridge.call_args.kwargs["news_source"],
            result.news_item["source"],
        )

    def test_plan_bridge_news_age_hours_from_news_item(self):
        result = self.run_dry(limit=3)
        self.assertEqual(
            self.m_plan_bridge.call_args.kwargs["news_age_hours"],
            result.news_item["age_hours"],
        )

    def test_plan_preserved_by_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.plan, self.m_plan_bridge.return_value)

    def test_validator_receives_exact_bridged_plan(self):
        result = self.run_dry(limit=3)
        self.assertIs(self.m_validate.call_args.args[0], result.plan)

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

    def test_no_legacy_planning_call_in_module(self):
        self.run_dry(limit=3)
        self.assertFalse(hasattr(pdr, "create_content_plan"))
        self.assertNotIn("create_content_plan", _code_text(SOURCE_PATH))


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

    def test_strategist_plan_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.strategist_plan)

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

    def test_news_bridge_not_called(self):
        self.run_dry(limit=3)
        self.m_news_bridge.assert_not_called()

    def test_run_strategist_not_called(self):
        self.run_dry(limit=3)
        self.m_strategist.assert_not_called()

    def test_plan_bridge_not_called(self):
        self.run_dry(limit=3)
        self.m_plan_bridge.assert_not_called()

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

    def test_news_bridge_exception_propagates(self):
        self.m_news_bridge.side_effect = ValueError(
            "strategic selection is not selected"
        )
        with self.assertRaisesRegex(ValueError, "strategic selection is not selected"):
            self.run_dry(limit=3)
        self.m_strategist.assert_not_called()

    def test_run_strategist_exception_propagates(self):
        self.m_strategist.side_effect = RuntimeError("strategist boom")
        with self.assertRaisesRegex(RuntimeError, "strategist boom"):
            self.run_dry(limit=3)
        self.m_plan_bridge.assert_not_called()
        self.m_validate.assert_not_called()

    def test_plan_bridge_exception_propagates(self):
        self.m_plan_bridge.side_effect = RuntimeError("bridge boom")
        with self.assertRaisesRegex(RuntimeError, "bridge boom"):
            self.run_dry(limit=3)
        self.m_validate.assert_not_called()

    def test_validator_exception_propagates(self):
        self.m_validate.side_effect = RuntimeError("validator boom")
        with self.assertRaisesRegex(RuntimeError, "validator boom"):
            self.run_dry(limit=3)

    def test_no_fallback_function_called_or_imported(self):
        # get_fallback_topic must not exist anywhere in the module.
        self.assertFalse(hasattr(pdr, "get_fallback_topic"))
        self.assertNotIn("get_fallback_topic", _code_text(SOURCE_PATH))


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
        self.news_item = (
            {"title": "VibeWorks CLI", "source": "github",
             "url": "https://github.com/vibeworks/cli", "age_hours": 0.27}
            if selected else None
        )
        self.strategist_plan = STRATEGIST_PLAN if selected else None
        self.plan = dict(PLAN) if selected else None
        self.validation = {"valid": True, "issues": []} if selected else None
        self.used_fallback = False
        self.stop_reason = None if selected else "no_selected_candidate"


def _section(text: str, header: str, next_header: str) -> str:
    """Return the report body between two section headers."""
    start = text.index(header)
    body = text[start + len(header):]
    end = body.index("\n" + next_header) if next_header is not None else len(body)
    return body[:end].strip()


class TestFormatter(unittest.TestCase):
    HEADER = "Researcher 2.0 -> SELECT -> Strategist 2.0 -> Legacy Bridge -> Validation"

    def test_header_is_exact_new_pipeline(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        self.assertIn(self.HEADER, text)

    def test_selected_section_reports_select_fields(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        section = _section(text, "\nSelected:", "\nLegacy news_item:")
        self.assertIn("title=VibeWorks CLI", section)
        self.assertIn("cluster=vibe_coding", section)
        self.assertIn("format=practical_guide", section)
        self.assertIn("research_required=False", section)
        self.assertIn("experiment_required=True", section)

    def test_recommended_format_none_renders_empty(self):
        fake = _FakeResult(selected=True)
        fake.selected_candidate.selection.recommended_format = None
        text = format_production_dry_run(fake)
        section = _section(text, "\nSelected:", "\nLegacy news_item:")
        self.assertIn("format=", section)

    def test_legacy_news_item_section_separate(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        section = _section(text, "\nLegacy news_item:", "\nStrategist 2.0:")
        self.assertIn("title=VibeWorks CLI", section)
        self.assertIn("source=github", section)
        self.assertIn("url=https://github.com/vibeworks/cli", section)
        self.assertIn("age_hours=0.27", section)

    def test_strategist_section_present(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        section = _section(text, "\nStrategist 2.0:", "\nPlan:")
        self.assertTrue(section)

    def test_strategist_section_reports_all_fields(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        section = _section(text, "\nStrategist 2.0:", "\nPlan:")
        self.assertIn("candidate_id=cand-42", section)
        self.assertIn("topic=VibeWorks CLI ships local agents", section)
        self.assertIn("cluster=vibe_coding", section)
        self.assertIn("format=practical_guide", section)
        self.assertIn("platforms=telegram,x", section)
        self.assertIn("research_required=False", section)
        self.assertIn("experiment_required=True", section)
        self.assertIn("angle=How it changes the practical dev process", section)
        self.assertIn("hook=VibeWorks CLI ships local agents", section)
        self.assertIn("objective=Teach the task step by step", section)
        self.assertIn("cta=Repeat the steps", section)
        self.assertIn("cta_link=https://example.com/winner", section)
        self.assertIn("tone=teaching and practical", section)
        self.assertIn("structure=hook,prerequisites,steps,result,cta", section)
        self.assertIn("language=ru", section)
        self.assertIn("mode=growth", section)

    def test_plan_section_reports_expanded_fields(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        section = _section(text, "\nPlan:", "\nValidation:")
        self.assertIn("topic=VibeWorks CLI ships local agents", section)
        self.assertIn("format=practical_guide", section)
        self.assertIn("content_format=practical_guide", section)
        self.assertIn("content_cluster=vibe_coding", section)
        self.assertIn("target_platforms=telegram,x", section)
        self.assertIn("research_required=False", section)
        self.assertIn("experiment_required=True", section)
        self.assertIn("angle=How it changes the practical dev process", section)
        self.assertIn("hook=VibeWorks CLI ships local agents", section)
        self.assertIn("objective=Teach the task step by step", section)
        self.assertIn("tone=teaching and practical", section)
        self.assertIn("structure=hook,prerequisites,steps,result,cta", section)
        self.assertIn("language=ru", section)
        self.assertIn("mode=growth", section)
        self.assertIn("platform=telegram", section)
        self.assertIn("cta=Repeat the steps", section)
        self.assertIn("cta_link=https://example.com/winner", section)

    def test_plan_section_has_no_product_block(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        section = _section(text, "\nPlan:", "\nValidation:")
        self.assertNotIn("product", section)
        self.assertNotIn("affiliate_link", section)
        self.assertNotIn("free_trial", section)

    def test_validation_section_reports_result(self):
        text = format_production_dry_run(_FakeResult(selected=True))
        section = _section(text, "\nValidation:", None)
        self.assertIn("valid=True", section)
        self.assertIn("issues=[]", section)

    def test_no_selected_renders_strategist_empty(self):
        text = format_production_dry_run(_FakeResult(selected=False))
        section = _section(text, "\nStrategist 2.0:", "\nPlan:")
        self.assertEqual(section, "(empty)")

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

    def test_formatter_does_not_call_run_strategist(self):
        with mock.patch.object(pdr, "run_strategist") as m_strategist:
            format_production_dry_run(_FakeResult(selected=True))
            m_strategist.assert_not_called()

    def test_formatter_does_not_call_plan_bridge(self):
        with mock.patch.object(pdr, "strategist_plan_to_legacy_plan") as m_bridge:
            format_production_dry_run(_FakeResult(selected=True))
            m_bridge.assert_not_called()

    def test_formatter_does_not_mutate_result(self):
        fake = _FakeResult(selected=True)
        snapshot_selected = fake.selected_candidate
        snapshot_news = fake.news_item
        snapshot_plan_obj = fake.strategist_plan
        snapshot_structure = fake.strategist_plan.structure
        snapshot_plan = fake.plan
        format_production_dry_run(fake)
        self.assertIs(fake.selected_candidate, snapshot_selected)
        self.assertIs(fake.news_item, snapshot_news)
        self.assertIs(fake.strategist_plan, snapshot_plan_obj)
        self.assertIs(fake.strategist_plan.structure, snapshot_structure)
        self.assertEqual(fake.plan, snapshot_plan)


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

    def test_no_create_content_plan_import_or_reference(self):
        self.assertNotIn("create_content_plan", self.text)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "src.agents.strategist")

    def test_imports_run_strategist(self):
        found = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "src.strategy.strategist"
            and any(alias.name == "run_strategist" for alias in node.names)
        ]
        self.assertEqual(len(found), 1)

    def test_imports_strategist_plan_to_legacy_plan(self):
        found = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "src.strategy.legacy_bridge"
            and any(
                alias.name == "strategist_plan_to_legacy_plan"
                for alias in node.names
            )
        ]
        self.assertEqual(len(found), 1)

    def test_imports_strategist_plan_type(self):
        found = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "src.domain.strategist"
            and any(alias.name == "StrategistPlan" for alias in node.names)
        ]
        self.assertEqual(len(found), 1)

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

    def test_exactly_one_run_strategist_call(self):
        fn = self._function("run_production_dry_run")
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "run_strategist"
        ]
        self.assertEqual(len(calls), 1)

    def test_exactly_one_strategist_plan_to_legacy_plan_call(self):
        fn = self._function("run_production_dry_run")
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "strategist_plan_to_legacy_plan"
        ]
        self.assertEqual(len(calls), 1)

    def test_no_lower_level_select_imports_or_calls(self):
        forbidden = (
            "select_research_result_winner", "select_shortlist_winner",
            "select_ranked_candidate", "build_selected_content_candidate",
        )
        for token in forbidden:
            self.assertNotIn(token, self.text)

    def test_no_get_fallback_topic(self):
        self.assertNotIn("get_fallback_topic", self.text)

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
                     "strategist_plan", "plan", "validation",
                     "used_fallback", "stop_reason"],
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

    def test_runner_has_no_datetime_now_call(self):
        fn = self._function("run_production_dry_run")
        now_calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "now"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "datetime"
        ]
        self.assertEqual(now_calls, [])

    def test_bridge_created_at_uses_now_isoformat(self):
        fn = self._function("run_production_dry_run")
        created_at = [
            node.value for node in ast.walk(fn)
            if isinstance(node, ast.keyword) and node.arg == "created_at"
        ]
        self.assertEqual(len(created_at), 1)
        call = created_at[0]
        self.assertIsInstance(call, ast.Call)
        self.assertIsInstance(call.func, ast.Attribute)
        self.assertEqual(call.func.attr, "isoformat")
        self.assertIsInstance(call.func.value, ast.Name)
        self.assertEqual(call.func.value.id, "now")

    def test_bridge_metadata_uses_exact_dict_indexing(self):
        fn = self._function("run_production_dry_run")
        keys = {
            node.slice.value for node in ast.walk(fn)
            if isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        }
        self.assertIn("source", keys)
        self.assertIn("age_hours", keys)

    def test_bridge_metadata_has_no_get_defaults(self):
        fn = self._function("run_production_dry_run")
        get_calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
        ]
        self.assertEqual(get_calls, [])


if __name__ == "__main__":
    unittest.main()
