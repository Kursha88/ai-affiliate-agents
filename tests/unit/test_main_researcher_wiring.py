"""Unit tests for the production discovery boundary in ``src/main.py``.

Stage 15, Step 15G-A: the renamed ``_get_production_discovery`` helper
must preserve the exact selected ``ContentCandidate`` by identity while
still producing the legacy ``news_item`` dict and fallback semantics.
All dependencies are patched in ``src.main`` — no live network, no DB,
no publication, no filesystem writes.

Stage 15, Step 15G-B: planning now branches on the discovery result —
a real selected candidate goes through Strategist 2.0
(``run_strategist`` → ``strategist_plan_to_legacy_plan``) and only a
genuine fallback discovery uses the legacy ``create_content_plan``.
"""

import dataclasses
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
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
from src.domain.strategist import StrategistPlan
from src.main import (
    _ProductionDiscovery,
    _get_production_discovery,
    _run_pipeline_inner,
)
from src.strategy.strategist import run_strategist
from src.strategy.legacy_bridge import strategist_plan_to_legacy_plan

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


def _make_strategist_plan() -> StrategistPlan:
    """A real StrategistPlan as run_strategist would return."""
    return StrategistPlan(
        candidate_id="c-1",
        topic="Selected AI Tool Story",
        content_cluster=ContentCluster.AI_TOOLS,
        content_format=ContentFormat.TOOL_DISCOVERY,
        target_platforms=(TargetPlatform.TELEGRAM,),
        research_required=False,
        experiment_required=False,
        angle="Как инструмент решает конкретную практическую проблему",
        hook="Selected AI Tool Story",
        objective="Показать, зачем нужен инструмент и где он полезен",
        cta="Изучить инструмент",
        cta_link="https://example.com/story?utm=x#frag",
        tone="практичный и конкретный",
        structure=("problem", "tool", "key_features", "use_case", "cta"),
        language="ru",
        mode="growth",
    )


def _bridged_plan() -> dict:
    """Minimal legacy dict as strategist_plan_to_legacy_plan would return."""
    return {
        "created_at": "2026-09-18T12:00:00+00:00",
        "mode": "growth",
        "platform": "telegram",
        "topic": "Selected AI Tool Story",
        "format": "tool_discovery",
        "news": {"source": "hacker_news", "url": "u", "age_hours": 2.0},
        "product": {
            "id": "source",
            "name": "Selected AI Tool Story",
            "description": "angle",
            "category": "Source",
            "affiliate_link": "https://example.com/story?utm=x#frag",
            "free_trial": False,
            "status": "active",
        },
        "language": "ru",
        "cta": "Изучить инструмент",
        "cta_link": "https://example.com/story?utm=x#frag",
        "is_affiliate": False,
    }


class TestSelectedPathPlanning(unittest.TestCase):
    """Selected candidate → Strategist 2.0 → legacy bridge (tests 25–34)."""

    def _run_pipeline(
        self,
        *,
        strategist_effect=None,
        bridge_effect=None,
        validation_result=None,
    ):
        discovery = _ProductionDiscovery(
            selected_candidate=_make_selected_candidate(),
            news_item=_real_news_item(),
            used_fallback=False,
        )
        plan = _make_strategist_plan()
        bridged = _bridged_plan()

        with ExitStack() as stack:
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}._get_production_discovery",
                    return_value=discovery,
                )
            )
            strategist_m = stack.enter_context(
                mock.patch(
                    f"{_MAIN}.run_strategist",
                    side_effect=strategist_effect
                    if strategist_effect is not None
                    else (lambda candidate: plan),
                )
            )
            bridge_m = stack.enter_context(
                mock.patch(
                    f"{_MAIN}.strategist_plan_to_legacy_plan",
                    side_effect=bridge_effect
                    if bridge_effect is not None
                    else (lambda strategist_plan, **kwargs: bridged),
                )
            )
            create_m = stack.enter_context(
                mock.patch(f"{_MAIN}.create_content_plan")
            )
            validation_m = stack.enter_context(
                mock.patch(
                    f"{_MAIN}.validate_content_plan",
                    return_value=validation_result
                    if validation_result is not None
                    else {"valid": True, "issues": []},
                )
            )
            state = mock.Mock()
            state.get_or_create_content_from_plan.return_value = (
                mock.Mock(),
                True,
            )
            state.get_or_create_publication.return_value = (
                mock.Mock(),
                True,
            )
            state.guard_publication.return_value = (True, "ok")
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.write_post",
                    side_effect=RuntimeError("stop-after-strategist"),
                )
            )
            log = mock.Mock()
            result = _run_pipeline_inner(state, "run-1", log)

        return {
            "result": result,
            "discovery": discovery,
            "plan": plan,
            "bridged": bridged,
            "strategist_m": strategist_m,
            "bridge_m": bridge_m,
            "create_m": create_m,
            "validation_m": validation_m,
            "state": state,
        }

    def test_25_selected_path_calls_run_strategist_exactly_once(self):
        ctx = self._run_pipeline()
        ctx["strategist_m"].assert_called_once()

    def test_26_exact_selected_candidate_passed_to_run_strategist(self):
        ctx = self._run_pipeline()
        ctx["strategist_m"].assert_called_once_with(
            ctx["discovery"].selected_candidate
        )

    def test_27_bridge_called_exactly_once(self):
        ctx = self._run_pipeline()
        ctx["bridge_m"].assert_called_once()

    def test_28_exact_strategist_plan_passed_to_bridge(self):
        ctx = self._run_pipeline()
        self.assertIs(ctx["bridge_m"].call_args.args[0], ctx["plan"])

    def test_29_bridge_receives_news_source_from_news_item(self):
        ctx = self._run_pipeline()
        self.assertEqual(
            ctx["bridge_m"].call_args.kwargs["news_source"],
            ctx["discovery"].news_item["source"],
        )

    def test_30_bridge_receives_news_age_hours_from_news_item(self):
        ctx = self._run_pipeline()
        self.assertEqual(
            ctx["bridge_m"].call_args.kwargs["news_age_hours"],
            ctx["discovery"].news_item["age_hours"],
        )

    def test_31_created_at_is_non_empty_iso_utc_timestamp(self):
        ctx = self._run_pipeline()
        created_at = ctx["bridge_m"].call_args.kwargs["created_at"]
        self.assertIsInstance(created_at, str)
        self.assertTrue(created_at)
        parsed = datetime.fromisoformat(created_at)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset(), timedelta(0))

    def test_32_selected_path_does_not_call_create_content_plan(self):
        ctx = self._run_pipeline()
        ctx["create_m"].assert_not_called()

    def test_33_bridge_result_is_exact_plan_validated(self):
        ctx = self._run_pipeline()
        self.assertIs(ctx["validation_m"].call_args.args[0], ctx["bridged"])

    def test_34_bridge_result_is_exact_plan_given_to_state(self):
        ctx = self._run_pipeline()
        ctx["state"].get_or_create_content_from_plan.assert_called_once()
        self.assertIs(
            ctx["state"].get_or_create_content_from_plan.call_args.args[0],
            ctx["bridged"],
        )


class TestFallbackPlanning(unittest.TestCase):
    """Genuine fallback discovery keeps the legacy planning path (35–38)."""

    def _run_pipeline(self, *, validation_result=None):
        discovery = _ProductionDiscovery(
            selected_candidate=None,
            news_item=_real_fallback(),
            used_fallback=True,
        )
        legacy_plan = _bridged_plan()

        with ExitStack() as stack:
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}._get_production_discovery",
                    return_value=discovery,
                )
            )
            strategist_m = stack.enter_context(
                mock.patch(f"{_MAIN}.run_strategist")
            )
            bridge_m = stack.enter_context(
                mock.patch(f"{_MAIN}.strategist_plan_to_legacy_plan")
            )
            create_m = stack.enter_context(
                mock.patch(
                    f"{_MAIN}.create_content_plan",
                    side_effect=lambda news_item=None: legacy_plan,
                )
            )
            validation_m = stack.enter_context(
                mock.patch(
                    f"{_MAIN}.validate_content_plan",
                    return_value=validation_result
                    if validation_result is not None
                    else {"valid": True, "issues": []},
                )
            )
            state = mock.Mock()
            state.get_or_create_content_from_plan.return_value = (
                mock.Mock(),
                True,
            )
            state.get_or_create_publication.return_value = (
                mock.Mock(),
                True,
            )
            state.guard_publication.return_value = (True, "ok")
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.write_post",
                    side_effect=RuntimeError("stop-after-strategist"),
                )
            )
            log = mock.Mock()
            result = _run_pipeline_inner(state, "run-1", log)

        return {
            "result": result,
            "discovery": discovery,
            "legacy_plan": legacy_plan,
            "strategist_m": strategist_m,
            "bridge_m": bridge_m,
            "create_m": create_m,
            "validation_m": validation_m,
            "state": state,
        }

    def test_35_fallback_calls_create_content_plan_with_news_item(self):
        ctx = self._run_pipeline()
        ctx["create_m"].assert_called_once_with(
            news_item=ctx["discovery"].news_item
        )

    def test_36_fallback_does_not_call_run_strategist(self):
        ctx = self._run_pipeline()
        ctx["strategist_m"].assert_not_called()

    def test_37_fallback_does_not_call_bridge(self):
        ctx = self._run_pipeline()
        ctx["bridge_m"].assert_not_called()

    def test_38_fallback_plan_still_validated(self):
        ctx = self._run_pipeline()
        ctx["validation_m"].assert_called_once()
        self.assertIs(
            ctx["validation_m"].call_args.args[0], ctx["legacy_plan"]
        )


class TestFailClosed(unittest.TestCase):
    """Strategist 2.0 failures never downgrade to legacy planning (39–44)."""

    def _run_selected_with_failure(
        self,
        *,
        strategist_effect=None,
        bridge_effect=None,
        validation_result=None,
    ):
        discovery = _ProductionDiscovery(
            selected_candidate=_make_selected_candidate(),
            news_item=_real_news_item(),
            used_fallback=False,
        )
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}._get_production_discovery",
                    return_value=discovery,
                )
            )
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.run_strategist",
                    side_effect=strategist_effect,
                )
            )
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.strategist_plan_to_legacy_plan",
                    side_effect=bridge_effect,
                )
            )
            create_m = stack.enter_context(
                mock.patch(f"{_MAIN}.create_content_plan")
            )
            stack.enter_context(
                mock.patch(
                    f"{_MAIN}.validate_content_plan",
                    return_value=validation_result
                    if validation_result is not None
                    else {"valid": True, "issues": []},
                )
            )
            state = mock.Mock()
            state.get_or_create_content_from_plan.return_value = (
                mock.Mock(),
                True,
            )
            state.get_or_create_publication.return_value = (
                mock.Mock(),
                True,
            )
            state.guard_publication.return_value = (True, "ok")
            log = mock.Mock()
            result = _run_pipeline_inner(state, "run-1", log)

        return result, create_m

    def test_39_run_strategist_exception_returns_strategist_failure(self):
        error = RuntimeError("strategist boom")
        result, _ = self._run_selected_with_failure(
            strategist_effect=error
        )
        self.assertIs(result["success"], False)
        self.assertEqual(result["step"], "strategist")
        self.assertIn("strategist boom", result["error"])

    def test_40_strategist_exception_does_not_call_create_content_plan(self):
        result, create_m = self._run_selected_with_failure(
            strategist_effect=RuntimeError("strategist boom")
        )
        create_m.assert_not_called()

    def test_41_bridge_exception_returns_strategist_failure(self):
        result, _ = self._run_selected_with_failure(
            bridge_effect=RuntimeError("bridge boom")
        )
        self.assertIs(result["success"], False)
        self.assertEqual(result["step"], "strategist")

    def test_42_bridge_exception_does_not_call_create_content_plan(self):
        result, create_m = self._run_selected_with_failure(
            bridge_effect=RuntimeError("bridge boom")
        )
        create_m.assert_not_called()

    def test_43_invalid_bridged_plan_returns_validation_failure(self):
        result, _ = self._run_selected_with_failure(
            bridge_effect=lambda *args, **kwargs: _bridged_plan(),
            validation_result={"valid": False, "issues": ["bad plan"]},
        )
        self.assertIs(result["success"], False)
        self.assertEqual(result["step"], "strategist")
        self.assertIn("bad plan", result["error"])

    def test_44_invalid_bridged_plan_does_not_call_create_content_plan(self):
        result, create_m = self._run_selected_with_failure(
            bridge_effect=lambda *args, **kwargs: _bridged_plan(),
            validation_result={"valid": False, "issues": ["bad plan"]},
        )
        create_m.assert_not_called()


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

    def test_45_main_imports_run_strategist(self):
        source = self._module_source()
        self.assertIn(
            "from src.strategy.strategist import run_strategist", source
        )

    def test_46_main_imports_strategist_plan_to_legacy_plan(self):
        source = self._module_source()
        self.assertIn(
            "from src.strategy.legacy_bridge import "
            "strategist_plan_to_legacy_plan",
            source,
        )

    def test_47_legacy_create_content_plan_import_still_exists(self):
        source = self._module_source()
        self.assertIn(
            "from src.agents.strategist import create_content_plan", source
        )

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
            "plan_validation = validate_content_plan(plan)",
            "state.get_or_create_content_from_plan(plan)",
            "state.guard_publication(publication)",
        ):
            self.assertIn(token, source)

    # ── Step 15G-B structural coverage (tests 48–55) ──────────────────

    def test_48_production_discovery_unchanged(self):
        self.assertTrue(dataclasses.is_dataclass(_ProductionDiscovery))
        self.assertTrue(_ProductionDiscovery.__dataclass_params__.frozen)
        self.assertEqual(
            [f.name for f in dataclasses.fields(_ProductionDiscovery)],
            ["selected_candidate", "news_item", "used_fallback"],
        )

    def test_49_discovery_helper_unchanged_in_responsibility(self):
        source = self._module_source()
        for token in (
            "def _get_production_discovery(",
            "Config.get_research_config()",
            "run_live_research(",
            "run_select_stage(",
            "content_candidate_to_news_item(",
            "get_fallback_topic()",
        ):
            self.assertIn(token, source)

    def test_50_no_content_candidate_construction_in_main(self):
        source = self._module_source()
        self.assertNotIn("ContentCandidate(", source)

    def test_51_no_policy_mappings_in_main(self):
        source = self._module_source()
        for token in ("ContentFormat", "ContentCluster"):
            self.assertNotIn(token, source)

    def test_52_branch_is_on_selected_candidate_presence(self):
        source = self._module_source()
        self.assertIn(
            "if discovery.selected_candidate is not None:", source
        )

    def test_53_create_content_plan_only_as_fallback_planning_call(self):
        source = self._module_source()
        call_lines = [
            line.strip()
            for line in source.splitlines()
            if "create_content_plan(" in line
        ]
        self.assertEqual(
            call_lines,
            ["plan = create_content_plan(news_item=news_item)"],
        )

    def test_54_no_fallback_downgrade_around_run_strategist(self):
        source = self._module_source()
        # run_strategist is called exactly once — the selected-path call —
        # with no nested try/except converting its failure into legacy
        # planning (the legacy call lives only in the else branch).
        self.assertEqual(source.count("run_strategist("), 1)
        self.assertIn(
            "strategist_plan = run_strategist(discovery.selected_candidate)",
            source,
        )
        lines = source.splitlines()
        branch_idx = next(
            i
            for i, line in enumerate(lines)
            if "if discovery.selected_candidate is not None:" in line
        )
        call_idx = next(
            i
            for i, line in enumerate(lines)
            if "run_strategist(discovery.selected_candidate)" in line
        )
        between = "\n".join(lines[branch_idx:call_idx])
        self.assertNotIn("try:", between)

    def test_55_downstream_plan_validation_and_state_references_present(self):
        source = self._module_source()
        for token in (
            "plan_validation = validate_content_plan(plan)",
            "state.get_or_create_content_from_plan(plan)",
            "state.guard_publication(publication)",
        ):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
