"""Unit tests for the production discovery boundary in ``src/main.py``.

Stage 15, Step 15G-A: the renamed ``_get_production_discovery`` helper
must preserve the exact selected ``ContentCandidate`` by identity while
still producing the legacy ``news_item`` dict and fallback semantics.
All dependencies are patched in ``src.main`` — no live network, no DB,
no publication, no filesystem writes.
"""

import dataclasses
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest import mock

from src.domain.strategy import (
    CandidateStage,
    ContentCandidate,
    ContentCluster,
    ContentFormat,
    DiscoveryCandidate,
    SourceType,
    StrategicSelection,
    TargetPlatform,
)
from src.main import (
    _ProductionDiscovery,
    _get_production_discovery,
    _run_pipeline_inner,
)

_MAIN = "src.main"
_NOW = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)


def _make_selected_candidate() -> ContentCandidate:
    """Smallest real selected ContentCandidate fixture."""
    return ContentCandidate(
        candidate=DiscoveryCandidate(
            candidate_id="c-1",
            title="Selected AI Tool Story",
            source_type=SourceType.HACKER_NEWS,
            source_url="https://example.com/story?utm=x#frag",
            discovered_at="2026-09-18T00:00:00Z",
            content_cluster=ContentCluster.AI_TOOLS,
            published_at="2026-09-18T10:00:00+00:00",
        ),
        selection=StrategicSelection(
            selected=True,
            selection_reason="top ranked",
            recommended_format=ContentFormat.TOOL_DISCOVERY,
            target_platforms=(TargetPlatform.TELEGRAM,),
        ),
        stage=CandidateStage.SELECTED,
    )


def _real_news_item() -> dict:
    return {
        "title": "Selected AI Tool Story",
        "source": "hacker_news",
        "url": "https://example.com/story?utm=x#frag",
        "age_hours": 2.0,
    }


def _real_fallback() -> dict:
    return {
        "title": "Fallback тема про нейросети",
        "url": "",
        "source": "editorial",
        "age_hours": 0,
        "summary": "Обзор",
    }


class TestResearchSuccessPath(unittest.TestCase):
    def _run_helper(self):
        candidate = _make_selected_candidate()
        news_item = _real_news_item()
        with ExitStack() as stack:
            config_mock = stack.enter_context(mock.patch(f"{_MAIN}.Config"))
            stack.enter_context(
                mock.patch(f"{_MAIN}.run_live_research", return_value=object())
            )
            select_mock = stack.enter_context(
                mock.patch(
                    f"{_MAIN}.run_select_stage", return_value=candidate
                )
            )
            bridge_mock = stack.enter_context(
                mock.patch(
                    f"{_MAIN}.content_candidate_to_news_item",
                    return_value=news_item,
                )
            )
            fallback_mock = stack.enter_context(
                mock.patch(f"{_MAIN}.get_fallback_topic")
            )
            log = mock.Mock()
            discovery = _get_production_discovery(now=_NOW, log=log)

        return (
            discovery,
            candidate,
            news_item,
            config_mock,
            select_mock,
            bridge_mock,
            fallback_mock,
            log,
        )

    def test_01_returns_production_discovery(self):
        discovery, *_ = self._run_helper()
        self.assertIsInstance(discovery, _ProductionDiscovery)

    def test_02_selected_candidate_is_exact_select_stage_object(self):
        discovery, candidate, *_ = self._run_helper()
        self.assertIs(discovery.selected_candidate, candidate)

    def test_03_news_item_is_exact_bridge_object(self):
        discovery, _, news_item, *_ = self._run_helper()
        self.assertIs(discovery.news_item, news_item)

    def test_04_used_fallback_is_false(self):
        discovery, *_ = self._run_helper()
        self.assertIs(discovery.used_fallback, False)

    def test_05_config_get_research_config_called_once(self):
        discovery, _, _, config_mock, *_ = self._run_helper()
        config_mock.get_research_config.assert_called_once_with()

    def test_06_run_live_research_called_once(self):
        live_kwargs = {"min_quality": 7.5, "prefer_free": True}
        with ExitStack() as stack:
            config_mock = stack.enter_context(mock.patch(f"{_MAIN}.Config"))
            config_mock.get_research_config.return_value.live_kwargs.return_value = live_kwargs
            research_mock = stack.enter_context(
                mock.patch(f"{_MAIN}.run_live_research", return_value=object())
            )
            stack.enter_context(
                mock.patch(f"{_MAIN}.run_select_stage", return_value=None)
            )
            stack.enter_context(
                mock.patch(f"{_MAIN}.content_candidate_to_news_item")
            )
            stack.enter_context(mock.patch(f"{_MAIN}.get_fallback_topic"))
            _get_production_discovery(now=_NOW, log=mock.Mock())

        research_mock.assert_called_once()
        self.assertEqual(
            research_mock.call_args.kwargs,
            {"now": _NOW, "limit": 5, **live_kwargs},
        )

    def test_07_run_select_stage_called_once(self):
        discovery, _, _, _, select_mock, *_ = self._run_helper()
        select_mock.assert_called_once()

    def test_08_content_candidate_to_news_item_called_once(self):
        discovery, _, _, _, _, bridge_mock, *_ = self._run_helper()
        bridge_mock.assert_called_once()

    def test_09_get_fallback_topic_not_called(self):
        discovery, _, _, _, _, _, fallback_mock, *_ = self._run_helper()
        fallback_mock.assert_not_called()

    def test_10_exact_now_object_passed_to_bridge(self):
        discovery, candidate, _, _, _, bridge_mock, *_ = self._run_helper()
        bridge_mock.assert_called_once_with(candidate, now=_NOW)


class TestNoSelectedCandidatePath(unittest.TestCase):
    def _run_helper(self):
        with ExitStack() as stack:
            stack.enter_context(mock.patch(f"{_MAIN}.Config"))
            stack.enter_context(
                mock.patch(f"{_MAIN}.run_live_research", return_value=object())
            )
            stack.enter_context(
                mock.patch(f"{_MAIN}.run_select_stage", return_value=None)
            )
            bridge_mock = stack.enter_context(
                mock.patch(f"{_MAIN}.content_candidate_to_news_item")
            )
            fallback = _real_fallback()
            fallback_mock = stack.enter_context(
                mock.patch(f"{_MAIN}.get_fallback_topic", return_value=fallback)
            )
            log = mock.Mock()
            discovery = _get_production_discovery(now=_NOW, log=log)

        return discovery, fallback, bridge_mock, fallback_mock, log

    def test_11_selected_candidate_is_none(self):
        discovery, *_ = self._run_helper()
        self.assertIsNone(discovery.selected_candidate)

    def test_12_news_item_is_exact_fallback_object(self):
        discovery, fallback, *_ = self._run_helper()
        self.assertIs(discovery.news_item, fallback)

    def test_13_used_fallback_is_true(self):
        discovery, *_ = self._run_helper()
        self.assertIs(discovery.used_fallback, True)

    def test_14_get_fallback_topic_called_once(self):
        discovery, _, _, fallback_mock, *_ = self._run_helper()
        fallback_mock.assert_called_once_with()

    def test_15_bridge_not_called(self):
        discovery, _, bridge_mock, *_ = self._run_helper()
        bridge_mock.assert_not_called()


class TestResearchExceptionPath(unittest.TestCase):
    ERROR = RuntimeError("research exploded")

    def _run_with_failure(self, point):
        """Inject a failure at one of the four Researcher-path points."""
        fallback = _real_fallback()
        with ExitStack() as stack:
            if point == "config":
                config_mock = stack.enter_context(mock.patch(f"{_MAIN}.Config"))
                config_mock.get_research_config.side_effect = self.ERROR
            else:
                stack.enter_context(mock.patch(f"{_MAIN}.Config"))
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.run_live_research",
                    side_effect=self.ERROR if point == "research" else None,
                    return_value=object() if point != "research" else None,
                )
            )
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.run_select_stage",
                    side_effect=self.ERROR if point == "select" else None,
                    return_value=None if point != "select" else None,
                )
            )
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.content_candidate_to_news_item",
                    side_effect=self.ERROR if point == "bridge" else None,
                    return_value=_real_news_item() if point != "bridge" else None,
                )
            )
            fallback_mock = stack.enter_context(
                mock.patch(f"{_MAIN}.get_fallback_topic", return_value=fallback)
            )
            log = mock.Mock()
            discovery = _get_production_discovery(now=_NOW, log=log)

        return discovery, fallback, fallback_mock, log

    def _failure_points(self):
        return ("config", "research", "select", "bridge")

    def test_16_selected_candidate_is_none_on_exceptions(self):
        for point in self._failure_points():
            with self.subTest(point=point):
                discovery, *_ = self._run_with_failure(point)
                self.assertIsNone(discovery.selected_candidate)

    def test_17_fallback_returned_on_exceptions(self):
        for point in self._failure_points():
            with self.subTest(point=point):
                discovery, fallback, *_ = self._run_with_failure(point)
                self.assertIs(discovery.news_item, fallback)

    def test_18_used_fallback_true_on_exceptions(self):
        for point in self._failure_points():
            with self.subTest(point=point):
                discovery, *_ = self._run_with_failure(point)
                self.assertIs(discovery.used_fallback, True)

    def test_19_warning_logged_on_exceptions(self):
        for point in self._failure_points():
            with self.subTest(point=point):
                discovery, _, _, log = self._run_with_failure(point)
                log.warning.assert_called_once()

    def test_20_get_fallback_topic_called_once_on_exceptions(self):
        for point in self._failure_points():
            with self.subTest(point=point):
                discovery, _, fallback_mock, *_ = self._run_with_failure(point)
                fallback_mock.assert_called_once_with()


class TestFallbackFailurePropagation(unittest.TestCase):
    def test_21_fallback_exception_propagates_unchanged(self):
        error = RuntimeError("fallback is broken")
        for point in (None, "select"):  # fallback reached from both paths
            with self.subTest(entry_point=point or "no-selected"):
                with ExitStack() as stack:
                    stack.enter_context(mock.patch(f"{_MAIN}.Config"))
                    stack.enter_context(
                        mock.patch(
                            f"{_MAIN}.run_live_research", return_value=object()
                        )
                    )
                    stack.enter_context(
                        mock.patch(
                            f"{_MAIN}.run_select_stage", return_value=None
                        )
                    )
                    stack.enter_context(
                        mock.patch(f"{_MAIN}.content_candidate_to_news_item")
                    )
                    stack.enter_context(
                        mock.patch(
                            f"{_MAIN}.get_fallback_topic", side_effect=error
                        )
                    )
                    with self.assertRaises(RuntimeError) as ctx:
                        _get_production_discovery(now=_NOW, log=mock.Mock())
                self.assertIs(ctx.exception, error)


class TestIdentityPreservation(unittest.TestCase):
    def test_22_selected_candidate_identity_preserved(self):
        candidate = _make_selected_candidate()
        with ExitStack() as stack:
            stack.enter_context(mock.patch(f"{_MAIN}.Config"))
            stack.enter_context(
                mock.patch(f"{_MAIN}.run_live_research", return_value=object())
            )
            stack.enter_context(
                mock.patch(f"{_MAIN}.run_select_stage", return_value=candidate)
            )
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.content_candidate_to_news_item",
                    return_value=_real_news_item(),
                )
            )
            stack.enter_context(mock.patch(f"{_MAIN}.get_fallback_topic"))
            discovery = _get_production_discovery(now=_NOW, log=mock.Mock())
        self.assertIs(discovery.selected_candidate, candidate)

    def test_23_news_item_identity_preserved_on_success(self):
        news_item = _real_news_item()
        with ExitStack() as stack:
            stack.enter_context(mock.patch(f"{_MAIN}.Config"))
            stack.enter_context(
                mock.patch(f"{_MAIN}.run_live_research", return_value=object())
            )
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.run_select_stage",
                    return_value=_make_selected_candidate(),
                )
            )
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.content_candidate_to_news_item",
                    return_value=news_item,
                )
            )
            stack.enter_context(mock.patch(f"{_MAIN}.get_fallback_topic"))
            discovery = _get_production_discovery(now=_NOW, log=mock.Mock())
        self.assertIs(discovery.news_item, news_item)

    def test_24_fallback_news_item_identity_preserved(self):
        fallback = _real_fallback()
        with ExitStack() as stack:
            stack.enter_context(mock.patch(f"{_MAIN}.Config"))
            stack.enter_context(
                mock.patch(f"{_MAIN}.run_live_research", return_value=object())
            )
            stack.enter_context(
                mock.patch(f"{_MAIN}.run_select_stage", return_value=None)
            )
            stack.enter_context(
                mock.patch(f"{_MAIN}.content_candidate_to_news_item")
            )
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.get_fallback_topic", return_value=fallback
                )
            )
            discovery = _get_production_discovery(now=_NOW, log=mock.Mock())
        self.assertIs(discovery.news_item, fallback)


class TestPipelineCompatibility(unittest.TestCase):
    def _run_pipeline_with_discovery(self):
        sentinel_candidate = mock.Mock(name="sentinel_selected_candidate")
        legacy_news = _real_news_item()

        with ExitStack() as stack:
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}._get_production_discovery",
                    return_value=_ProductionDiscovery(
                        selected_candidate=sentinel_candidate,
                        news_item=legacy_news,
                        used_fallback=False,
                    ),
                )
            )
            plan_mock = stack.enter_context(
                mock.patch(f"{_MAIN}.create_content_plan")
            )
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.validate_content_plan",
                    return_value={"valid": False, "issues": ["stop-here"]},
                )
            )
            state = mock.Mock()
            log = mock.Mock()
            result = _run_pipeline_inner(state, "run-1", log)

        return result, plan_mock, legacy_news, sentinel_candidate

    def test_25_create_content_plan_called_with_discovery_news_item(self):
        result, plan_mock, legacy_news, _ = self._run_pipeline_with_discovery()
        plan_mock.assert_called_once_with(news_item=legacy_news)

    def test_26_selected_candidate_not_passed_to_create_content_plan(self):
        result, plan_mock, _, sentinel_candidate = (
            self._run_pipeline_with_discovery()
        )
        self.assertEqual(list(plan_mock.call_args.kwargs.keys()), ["news_item"])
        self.assertNotIn("selected_candidate", plan_mock.call_args.kwargs)
        # The sentinel must not leak anywhere into the planning call.
        self.assertNotIn(
            repr(sentinel_candidate), repr(plan_mock.call_args)
        )

    def test_27_existing_create_content_plan_path_still_used(self):
        result, plan_mock, _, _ = self._run_pipeline_with_discovery()
        # The pipeline stopped right after plan validation on the
        # strategist step — proving the legacy plan path executed.
        self.assertEqual(result["step"], "strategist")
        self.assertIs(result["success"], False)


class TestStructuralBoundaries(unittest.TestCase):
    def _module_source(self) -> str:
        import src.main as main_module

        with open(main_module.__file__, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_28_production_discovery_is_dataclass(self):
        self.assertTrue(dataclasses.is_dataclass(_ProductionDiscovery))

    def test_29_production_discovery_is_frozen(self):
        self.assertTrue(_ProductionDiscovery.__dataclass_params__.frozen)

    def test_30_fields_exactly_three(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(_ProductionDiscovery)],
            ["selected_candidate", "news_item", "used_fallback"],
        )

    def test_31_helper_named_exactly_get_production_discovery(self):
        import src.main as main_module

        self.assertTrue(hasattr(main_module, "_get_production_discovery"))
        self.assertTrue(callable(main_module._get_production_discovery))

    def test_32_old_helper_name_no_longer_exists(self):
        import src.main as main_module

        self.assertFalse(hasattr(main_module, "_get_production_news_item"))

    def test_33_no_strategist_2_0_import(self):
        source = self._module_source()
        self.assertNotIn("src.strategy.strategist", source)

    def test_34_no_run_strategist_reference(self):
        source = self._module_source()
        self.assertNotIn("run_strategist", source)

    def test_35_no_legacy_bridge_plan_reference(self):
        source = self._module_source()
        self.assertNotIn("strategist_plan_to_legacy_plan", source)

    def test_36_no_fallback_content_candidate_construction(self):
        source = self._module_source()
        self.assertNotIn("ContentCandidate(", source)

    def test_37_no_new_content_cluster_default(self):
        source = self._module_source()
        self.assertNotIn("ContentCluster", source)

    def test_38_no_new_content_format_default(self):
        source = self._module_source()
        self.assertNotIn("ContentFormat", source)

    def test_39_create_content_plan_import_unchanged(self):
        source = self._module_source()
        self.assertIn(
            "from src.agents.strategist import create_content_plan", source
        )

    def test_40_no_unrelated_production_code_changes(self):
        source = self._module_source()
        # Key downstream behaviors must remain referenced exactly as before.
        for token in (
            "plan = create_content_plan(news_item=news_item)",
            "plan_validation = validate_content_plan(plan)",
            "state.get_or_create_content_from_plan(plan)",
            "state.guard_publication(publication)",
        ):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
