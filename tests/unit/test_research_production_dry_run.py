"""Step 15H-A unit tests: live end-to-end production dry run.

Regression coverage, migrated in Step 15H-A-FIX to the Strategist 2.0 contract
(run_live_research -> run_select_stage -> content_candidate_to_news_item ->
run_strategist -> strategist_plan_to_legacy_plan -> validate_content_plan).
Patches every dependency WHERE USED in ``src.research.production_dry_run``:
Config, run_live_research, run_select_stage, content_candidate_to_news_item,
run_strategist, strategist_plan_to_legacy_plan, validate_content_plan. No live
network, no filesystem writes, no real Strategist execution. Full new-path
coverage lives in tests/unit/test_production_dry_run_select_path.py.
Structural AST tests bind the side-effect boundaries to actual code
(docstring-immune by construction).
"""

import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from src.domain.strategy import ContentCluster, ContentFormat, TargetPlatform
from src.domain.strategist import StrategistPlan
from src.research import production_dry_run as pdr

SOURCE_PATH = Path(__file__).resolve().parents[2] / "src" / "research" / "production_dry_run.py"

NOW = datetime(2026, 9, 18, 18, 0, 0, tzinfo=timezone.utc)
NEWS_ITEM = {
    "title": "Test Research Candidate",
    "source": "github",
    "url": "https://example.com/item",
    "age_hours": 2.5,
}
PLAN_STRUCTURE = ("hook", "prerequisites", "steps", "result", "cta")
PLAN_PLATFORMS = ("telegram", "x")
STRATEGIST_PLAN = StrategistPlan(
    candidate_id="cand-42",
    topic="VibeWorks CLI ships local agents",
    content_cluster=ContentCluster.VIBE_CODING,
    content_format=ContentFormat.PRACTICAL_GUIDE,
    target_platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
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
    "topic": "VibeWorks CLI ships local agents",
    "format": "practical_guide",
    "content_format": "practical_guide",
    "content_cluster": "vibe_coding",
    "target_platforms": PLAN_PLATFORMS,
    "research_required": False,
    "experiment_required": True,
    "angle": "How it changes the practical dev process",
    "hook": "VibeWorks CLI ships local agents",
    "objective": "Teach the task step by step",
    "tone": "teaching and practical",
    "structure": PLAN_STRUCTURE,
    "language": "ru",
    "mode": "growth",
    "platform": "telegram",
    "cta": "Repeat the steps",
    "cta_link": "https://example.com/winner",
    # Product may exist in the bridged plan, but the formatter must not rely on it.
    "product": {"id": "pro"},
}
LIVE_KWARGS = {
    "blog_feeds": ("blog",),
    "docs_feeds": ("docs",),
    "trusted_primary_domains": ("example.com",),
}


class _Harness(unittest.TestCase):
    """Shared patch harness with identity sentinels for every boundary."""

    def setUp(self):
        self.research_result = object()  # identity sentinel
        self.selected_candidate = object()  # identity sentinel
        self.validation = {"valid": True, "issues": []}

        self.config = mock.Mock()
        self.config.live_kwargs.return_value = dict(LIVE_KWARGS)
        self.m_config = mock.patch.object(pdr, "Config").start()
        self.m_config.get_research_config.return_value = self.config

        self.m_run_live = mock.patch.object(
            pdr, "run_live_research", return_value=self.research_result
        ).start()
        self.m_select = mock.patch.object(
            pdr, "run_select_stage", return_value=self.selected_candidate
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
            pdr, "validate_content_plan", return_value=self.validation
        ).start()
        self.addCleanup(mock.patch.stopall)

    def run_dry(self, **kwargs):
        return pdr.run_production_dry_run(now=NOW, **kwargs)


class TestSuccessfulPath(_Harness):
    def test_config_get_research_config_called_exactly_once(self):
        self.run_dry(limit=3)
        self.m_config.get_research_config.assert_called_once()

    def test_config_live_kwargs_called_exactly_once(self):
        self.run_dry(limit=3)
        self.config.live_kwargs.assert_called_once()

    def test_run_live_research_called_exactly_once(self):
        self.run_dry(limit=3)
        self.m_run_live.assert_called_once()

    def test_exact_now_forwarded_to_run_live_research(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_run_live.call_args.kwargs["now"], NOW)

    def test_exact_limit_forwarded(self):
        self.run_dry(limit=7)
        self.assertEqual(self.m_run_live.call_args.kwargs["limit"], 7)

    def test_exact_live_kwargs_forwarded(self):
        self.run_dry(limit=3)
        kwargs = self.m_run_live.call_args.kwargs
        self.assertEqual(kwargs["blog_feeds"], LIVE_KWARGS["blog_feeds"])
        self.assertEqual(kwargs["docs_feeds"], LIVE_KWARGS["docs_feeds"])
        self.assertEqual(
            kwargs["trusted_primary_domains"], LIVE_KWARGS["trusted_primary_domains"]
        )

    def test_select_stage_called_exactly_once(self):
        self.run_dry(limit=3)
        self.m_select.assert_called_once()

    def test_select_stage_receives_same_research_result_object(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_select.call_args.args[0], self.research_result)

    def test_news_bridge_called_exactly_once(self):
        self.run_dry(limit=3)
        self.m_news_bridge.assert_called_once()

    def test_news_bridge_receives_same_selected_candidate_object(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_news_bridge.call_args.args[0], self.selected_candidate)

    def test_news_bridge_receives_same_injected_now(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_news_bridge.call_args.kwargs["now"], NOW)

    def test_run_strategist_called_exactly_once(self):
        self.run_dry(limit=3)
        self.m_strategist.assert_called_once()

    def test_run_strategist_receives_exact_selected_candidate(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_strategist.call_args.args[0], self.selected_candidate)

    def test_plan_bridge_called_exactly_once(self):
        self.run_dry(limit=3)
        self.m_plan_bridge.assert_called_once()

    def test_plan_bridge_receives_exact_strategist_plan_object(self):
        self.run_dry(limit=3)
        self.assertIs(self.m_plan_bridge.call_args.args[0], STRATEGIST_PLAN)

    def test_plan_bridge_created_at_is_now_isoformat(self):
        self.run_dry(limit=3)
        self.assertEqual(
            self.m_plan_bridge.call_args.kwargs["created_at"], NOW.isoformat()
        )

    def test_plan_bridge_news_source_from_news_item(self):
        self.run_dry(limit=3)
        self.assertEqual(
            self.m_plan_bridge.call_args.kwargs["news_source"], NEWS_ITEM["source"]
        )

    def test_plan_bridge_news_age_hours_from_news_item(self):
        self.run_dry(limit=3)
        self.assertEqual(
            self.m_plan_bridge.call_args.kwargs["news_age_hours"],
            NEWS_ITEM["age_hours"],
        )

    def test_validate_content_plan_receives_exact_bridged_plan(self):
        result = self.run_dry(limit=3)
        self.assertIs(self.m_validate.call_args.args[0], result.plan)

    def test_result_preserves_research_result_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.research_result, self.research_result)

    def test_result_preserves_selected_candidate_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.selected_candidate, self.selected_candidate)

    def test_result_preserves_news_item_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.news_item, self.m_news_bridge.return_value)

    def test_result_preserves_strategist_plan_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.strategist_plan, STRATEGIST_PLAN)
        self.assertIs(result.strategist_plan, self.m_strategist.return_value)

    def test_result_preserves_plan_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.plan, self.m_plan_bridge.return_value)

    def test_result_preserves_validation_identity(self):
        result = self.run_dry(limit=3)
        self.assertIs(result.validation, self.validation)

    def test_used_fallback_is_always_false(self):
        ok = self.run_dry(limit=3)
        self.assertFalse(ok.used_fallback)

    def test_stop_reason_is_none_on_success(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.stop_reason)


class TestNoSelectedCandidatePath(_Harness):
    """SELECT stage returned no winner -> bridge/strategist/validator skipped."""

    def setUp(self):
        super().setUp()
        self.m_select.return_value = None

    def test_selected_candidate_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.selected_candidate)

    def test_result_news_item_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.news_item)

    def test_result_strategist_plan_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.strategist_plan)

    def test_result_plan_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.plan)

    def test_result_validation_is_none(self):
        result = self.run_dry(limit=3)
        self.assertIsNone(result.validation)

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

    def test_stop_reason_no_selected_candidate(self):
        result = self.run_dry(limit=3)
        self.assertEqual(result.stop_reason, "no_selected_candidate")

    def test_used_fallback_still_false(self):
        result = self.run_dry(limit=3)
        self.assertFalse(result.used_fallback)


class TestValidationFailureExposed(_Harness):
    def test_invalid_validation_returned_unchanged_without_raising(self):
        failed = {"valid": False, "issues": ["x"]}
        self.m_validate.return_value = failed
        result = self.run_dry(limit=3)
        self.assertIs(result.validation, failed)
        self.assertEqual(result.validation, {"valid": False, "issues": ["x"]})
        self.assertIsNone(result.stop_reason)


class TestExceptionPropagation(_Harness):
    def test_config_exception_propagates(self):
        self.m_config.get_research_config.side_effect = RuntimeError("cfg boom")
        with self.assertRaisesRegex(RuntimeError, "cfg boom"):
            self.run_dry(limit=3)

    def test_researcher_exception_propagates(self):
        self.m_run_live.side_effect = RuntimeError("research boom")
        with self.assertRaisesRegex(RuntimeError, "research boom"):
            self.run_dry(limit=3)

    def test_select_stage_exception_propagates(self):
        self.m_select.side_effect = ValueError("select boom")
        with self.assertRaisesRegex(ValueError, "select boom"):
            self.run_dry(limit=3)

    def test_news_bridge_exception_propagates(self):
        self.m_news_bridge.side_effect = RuntimeError("bridge boom")
        with self.assertRaisesRegex(RuntimeError, "bridge boom"):
            self.run_dry(limit=3)

    def test_strategist_exception_propagates(self):
        self.m_strategist.side_effect = RuntimeError("strategist boom")
        with self.assertRaisesRegex(RuntimeError, "strategist boom"):
            self.run_dry(limit=3)

    def test_plan_bridge_exception_propagates(self):
        self.m_plan_bridge.side_effect = RuntimeError("plan bridge boom")
        with self.assertRaisesRegex(RuntimeError, "plan bridge boom"):
            self.run_dry(limit=3)

    def test_validator_exception_propagates(self):
        self.m_validate.side_effect = RuntimeError("validator boom")
        with self.assertRaisesRegex(RuntimeError, "validator boom"):
            self.run_dry(limit=3)


class _FakeRanked:
    def __init__(self, n):
        self.ranked = tuple(object() for _ in range(n))


class _FakeResearch:
    input_count = 11
    deduplicated_count = 10
    classified_count = 10
    verified_count = 10
    scored_count = 10

    def __init__(self, ranked_count=8):
        self.ranked = _FakeRanked(ranked_count)


class _FakeCluster:
    value = "vibe_coding"


class _FakeFormat:
    value = "practical_guide"


class _FakeSelection:
    def __init__(self):
        self.recommended_format = _FakeFormat()
        self.research_required = False
        self.experiment_required = True


class _FakeDiscovery:
    def __init__(self):
        self.title = "VibeWorks CLI"
        self.content_cluster = _FakeCluster()


class _FakeSelected:
    def __init__(self):
        self.candidate = _FakeDiscovery()
        self.selection = _FakeSelection()


def _full_result(**overrides):
    kwargs = dict(
        research_result=_FakeResearch(),
        selected_candidate=_FakeSelected(),
        news_item=dict(NEWS_ITEM),
        strategist_plan=STRATEGIST_PLAN,
        plan=dict(PLAN),
        validation={"valid": True, "issues": []},
        used_fallback=False,
        stop_reason=None,
    )
    kwargs.update(overrides)
    return pdr.ProductionDryRunResult(**kwargs)


class TestFormatter(unittest.TestCase):
    HEADER = "Researcher 2.0 -> SELECT -> Strategist 2.0 -> Legacy Bridge -> Validation"

    def test_contains_exact_research_counts(self):
        text = pdr.format_production_dry_run(_full_result())
        self.assertIn(self.HEADER, text)
        self.assertIn("input=11", text)
        self.assertIn("deduplicated=10", text)
        self.assertIn("classified=10", text)
        self.assertIn("verified=10", text)
        self.assertIn("scored=10", text)
        self.assertIn("ranked=8", text)

    def test_selected_section_comes_from_selected_candidate(self):
        text = pdr.format_production_dry_run(_full_result())
        self.assertIn("title=VibeWorks CLI", text)
        self.assertIn("cluster=vibe_coding", text)
        self.assertIn("format=practical_guide", text)
        self.assertIn("research_required=False", text)
        self.assertIn("experiment_required=True", text)

    def test_contains_legacy_news_item_fields(self):
        text = pdr.format_production_dry_run(_full_result())
        self.assertIn("Legacy news_item:", text)
        self.assertIn(f"title={NEWS_ITEM['title']}", text)
        self.assertIn(f"source={NEWS_ITEM['source']}", text)
        self.assertIn(f"url={NEWS_ITEM['url']}", text)
        self.assertIn(f"age_hours={NEWS_ITEM['age_hours']}", text)

    def test_contains_strategist_2_0_section(self):
        text = pdr.format_production_dry_run(_full_result())
        self.assertIn("Strategist 2.0:", text)
        self.assertIn(f"candidate_id={STRATEGIST_PLAN.candidate_id}", text)
        self.assertIn(f"cluster={STRATEGIST_PLAN.content_cluster.value}", text)
        self.assertIn(f"format={STRATEGIST_PLAN.content_format.value}", text)
        self.assertIn(
            "platforms=" + ",".join(p.value for p in STRATEGIST_PLAN.target_platforms),
            text,
        )
        self.assertIn(f"angle={STRATEGIST_PLAN.angle}", text)
        self.assertIn(f"mode={STRATEGIST_PLAN.mode}", text)

    def test_contains_plan_fields(self):
        text = pdr.format_production_dry_run(_full_result())
        self.assertIn(f"topic={PLAN['topic']}", text)
        self.assertIn(f"format={PLAN['format']}", text)
        self.assertIn(f"content_format={PLAN['content_format']}", text)
        self.assertIn(f"content_cluster={PLAN['content_cluster']}", text)
        self.assertIn("target_platforms=" + ",".join(PLAN["target_platforms"]), text)
        self.assertIn(f"research_required={PLAN['research_required']}", text)
        self.assertIn(f"experiment_required={PLAN['experiment_required']}", text)
        self.assertIn(f"angle={PLAN['angle']}", text)
        self.assertIn(f"hook={PLAN['hook']}", text)
        self.assertIn(f"objective={PLAN['objective']}", text)
        self.assertIn(f"tone={PLAN['tone']}", text)
        self.assertIn("structure=" + ",".join(PLAN["structure"]), text)
        self.assertIn(f"language={PLAN['language']}", text)
        self.assertIn(f"mode={PLAN['mode']}", text)
        self.assertIn(f"platform={PLAN['platform']}", text)
        self.assertIn(f"cta={PLAN['cta']}", text)
        self.assertIn(f"cta_link={PLAN['cta_link']}", text)
        # Product exists in PLAN but the formatter must not render it.
        self.assertNotIn("product", text)

    def test_contains_validation_fields(self):
        text = pdr.format_production_dry_run(_full_result())
        self.assertIn("valid=True", text)
        self.assertIn("issues=[]", text)

    def test_no_selected_candidate_report(self):
        text = pdr.format_production_dry_run(
            _full_result(selected_candidate=None, news_item=None,
                         strategist_plan=None, plan=None, validation=None,
                         stop_reason="no_selected_candidate")
        )
        self.assertIn("(empty)", text)
        self.assertIn("stop_reason=no_selected_candidate", text)


def _tree():
    return ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))


def _identifiers(tree):
    """All Name ids, Attribute attrs, and import names (docstring-immune)."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            ids.add(node.id)
        elif isinstance(node, ast.Attribute):
            ids.add(node.attr)
        elif isinstance(node, ast.Import):
            ids.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                ids.add(node.module)
            ids.update(a.name for a in node.names)
    return ids


def _call_func_name(call):
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _enclosing_functions(tree):
    """Map child node -> nearest enclosing FunctionDef/AsyncFunctionDef."""
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def nearest_func(node):
        while node is not None:
            node = parents.get(node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
        return None

    return nearest_func


class TestStructuralBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _tree()
        cls.ids = _identifiers(cls.tree)

    def _function(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        raise AssertionError(f"{name} not found")

    def test_no_create_content_plan_import_or_reference(self):
        self.assertNotIn("create_content_plan", self.ids)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "src.agents.strategist")

    def test_strategist_2_0_entry_points_present(self):
        self.assertIn("run_strategist", self.ids)
        self.assertIn("strategist_plan_to_legacy_plan", self.ids)

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

    def test_no_forbidden_modules_or_names(self):
        forbidden = {
            "get_fallback_topic", "StateService", "state_service", "sqlite3",
            "publisher", "Publisher", "copywriter", "Copywriter",
            "editor", "Editor", "designer", "Designer",
            "telegram", "Telegram", "ContentItem", "Publication",
            "twitter", "vk", "pinterest",
            "research_result_to_news_item",
            "select_research_result_winner", "select_shortlist_winner",
            "select_ranked_candidate", "build_selected_content_candidate",
        }
        leaks = sorted(i for i in self.ids if i in forbidden)
        self.assertEqual(leaks, [])

    def test_select_stage_entry_points_present(self):
        self.assertIn("run_select_stage", self.ids)
        self.assertIn("content_candidate_to_news_item", self.ids)

    def test_no_filesystem_write(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                self.assertNotEqual(_call_func_name(node), "open")
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn(node.module, {"os", "pathlib", "shutil"})
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], {"os", "pathlib", "shutil"})

    def test_datetime_now_only_inside_main(self):
        nearest = _enclosing_functions(self.tree)
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "now"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "datetime"
            ):
                self.assertIs(nearest(node).name, "main")

    def test_no_pipeline_stage_calls(self):
        forbidden_patterns = ("score", "rank", "classif", "verif", "fetch")
        calls = {
            name for n in ast.walk(self.tree) if isinstance(n, ast.Call)
            for name in [_call_func_name(n)] if name
        }
        leaks = sorted(
            c for c in calls
            if any(p in c.lower() for p in forbidden_patterns)
        )
        self.assertEqual(leaks, [])


if __name__ == "__main__":
    unittest.main()
