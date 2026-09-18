"""Unit tests for the lossless StrategistPlan → legacy bridge (Step 15F).

Covers exact field mapping, losslessness (enum .value serialization,
structure tuple identity, platform order), compatibility metadata
handling, the neutral product block, real ``validate_content_plan``
compatibility, required keyword-only arguments and the structural
boundaries of ``src/strategy/legacy_bridge.py``.
"""

import inspect
import unittest
from dataclasses import replace

from src.domain.strategy import (
    ContentCluster,
    ContentFormat,
    TargetPlatform,
)
from src.domain.strategist import StrategistPlan
from src.strategy import legacy_bridge
from src.utils.validators import validate_content_plan

_BRIDGE_MODULE = "src.strategy.legacy_bridge"

_CREATED_AT = "2026-09-18T12:00:00Z"
_NEWS_SOURCE = "Hacker News"
_NEWS_AGE_HOURS = 3.5

_EXPECTED_TOP_LEVEL_KEYS = frozenset(
    {
        "created_at",
        "mode",
        "platform",
        "candidate_id",
        "topic",
        "format",
        "content_format",
        "content_cluster",
        "target_platforms",
        "research_required",
        "experiment_required",
        "angle",
        "hook",
        "objective",
        "tone",
        "structure",
        "news",
        "product",
        "language",
        "cta",
        "cta_link",
        "is_affiliate",
    }
)


def _make_plan(
    fmt=ContentFormat.WORKFLOW,
    cluster=ContentCluster.AI_TOOLS,
    platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
    research_required=False,
    experiment_required=False,
    title="Как автоматизировать рутину с помощью AI",
    angle="Как автоматизировать повторяемую работу и сократить ручные действия",
    topic_suffix="",
):
    return StrategistPlan(
        candidate_id="c-2026-001",
        topic=title + topic_suffix,
        content_cluster=cluster,
        content_format=fmt,
        target_platforms=platforms,
        research_required=research_required,
        experiment_required=experiment_required,
        angle=angle,
        hook=title + topic_suffix,
        objective="Показать повторяемый рабочий процесс от задачи до результата",
        cta="Попробовать этот процесс",
        cta_link="https://example.com/source-article?utm=none#section",
        tone="системный и практичный",
        structure=("problem", "workflow", "steps", "result", "cta"),
        language="ru",
        mode="growth",
    )


def _bridge(
    plan=None,
    created_at=_CREATED_AT,
    news_source=_NEWS_SOURCE,
    news_age_hours=_NEWS_AGE_HOURS,
):
    return legacy_bridge.strategist_plan_to_legacy_plan(
        plan if plan is not None else _make_plan(),
        created_at=created_at,
        news_source=news_source,
        news_age_hours=news_age_hours,
    )


class TestBasic(unittest.TestCase):
    def test_01_returns_dict(self):
        result = _bridge()
        self.assertIsInstance(result, dict)

    def test_02_top_level_keys_exactly_required_set(self):
        result = _bridge()
        self.assertEqual(frozenset(result.keys()), _EXPECTED_TOP_LEVEL_KEYS)

    def test_03_deterministic_for_same_inputs(self):
        plan = _make_plan()
        first = _bridge(plan=plan)
        second = _bridge(plan=plan)
        self.assertEqual(first, second)


class TestCoreLegacyCompatibility(unittest.TestCase):
    def setUp(self):
        self.plan = _make_plan()
        self.result = _bridge(plan=self.plan)

    def test_04_topic_exact(self):
        self.assertEqual(self.result["topic"], self.plan.topic)

    def test_05_format_equals_format_value(self):
        self.assertEqual(self.result["format"], self.plan.content_format.value)

    def test_06_platform_is_telegram(self):
        self.assertEqual(self.result["platform"], "telegram")

    def test_07_mode_exact(self):
        self.assertEqual(self.result["mode"], self.plan.mode)

    def test_08_language_exact(self):
        self.assertEqual(self.result["language"], self.plan.language)

    def test_09_cta_exact(self):
        self.assertEqual(self.result["cta"], self.plan.cta)

    def test_10_cta_link_exact(self):
        self.assertEqual(self.result["cta_link"], self.plan.cta_link)


class TestModernDataPreservation(unittest.TestCase):
    def setUp(self):
        self.plan = _make_plan()
        self.result = _bridge(plan=self.plan)

    def test_11_candidate_id_exact(self):
        self.assertEqual(self.result["candidate_id"], self.plan.candidate_id)

    def test_12_content_format_exact(self):
        self.assertEqual(self.result["content_format"], self.plan.content_format.value)

    def test_13_content_cluster_exact(self):
        self.assertEqual(self.result["content_cluster"], self.plan.content_cluster.value)

    def test_14_target_platforms_values_exact(self):
        self.assertEqual(
            self.result["target_platforms"],
            tuple(p.value for p in self.plan.target_platforms),
        )

    def test_15_target_platform_order_preserved(self):
        self.assertEqual(
            self.result["target_platforms"],
            ("telegram", "x"),
        )

    def test_16_research_required_exact(self):
        self.assertEqual(
            self.result["research_required"], self.plan.research_required
        )

    def test_17_experiment_required_exact(self):
        self.assertEqual(
            self.result["experiment_required"], self.plan.experiment_required
        )

    def test_18_angle_exact(self):
        self.assertEqual(self.result["angle"], self.plan.angle)

    def test_19_hook_exact(self):
        self.assertEqual(self.result["hook"], self.plan.hook)

    def test_20_objective_exact(self):
        self.assertEqual(self.result["objective"], self.plan.objective)

    def test_21_tone_exact(self):
        self.assertEqual(self.result["tone"], self.plan.tone)

    def test_22_structure_exact_by_value(self):
        self.assertEqual(self.result["structure"], self.plan.structure)

    def test_23_structure_preserved_by_identity(self):
        self.assertIs(self.result["structure"], self.plan.structure)

    def test_24_all_flag_combinations_preserved(self):
        for research in (False, True):
            for experiment in (False, True):
                with self.subTest(research=research, experiment=experiment):
                    plan = _make_plan(
                        research_required=research,
                        experiment_required=experiment,
                    )
                    result = _bridge(plan=plan)
                    self.assertEqual(result["research_required"], research)
                    self.assertEqual(result["experiment_required"], experiment)

    def test_25_every_content_format_serializes_to_own_value(self):
        for fmt in ContentFormat:
            with self.subTest(format=fmt.value):
                plan = _make_plan(fmt=fmt)
                result = _bridge(plan=plan)
                self.assertEqual(result["format"], fmt.value)
                self.assertEqual(result["content_format"], fmt.value)

    def test_26_every_content_cluster_serializes_to_own_value(self):
        for cluster in ContentCluster:
            with self.subTest(cluster=cluster.value):
                plan = _make_plan(cluster=cluster)
                result = _bridge(plan=plan)
                self.assertEqual(result["content_cluster"], cluster.value)

    def test_27_every_target_platform_serializes_to_own_value(self):
        for platform in TargetPlatform:
            with self.subTest(platform=platform.value):
                plan = _make_plan(platforms=(platform,))
                result = _bridge(plan=plan)
                self.assertEqual(result["target_platforms"], (platform.value,))


class TestCompatibilityMetadata(unittest.TestCase):
    def test_28_created_at_exact(self):
        self.assertEqual(_bridge()["created_at"], _CREATED_AT)

    def test_29_news_source_exact(self):
        result = _bridge()
        self.assertEqual(result["news"]["source"], _NEWS_SOURCE)

    def test_30_news_url_equals_plan_cta_link(self):
        plan = _make_plan()
        result = _bridge(plan=plan)
        self.assertEqual(result["news"]["url"], plan.cta_link)

    def test_31_news_age_hours_exact(self):
        result = _bridge()
        self.assertEqual(result["news"]["age_hours"], _NEWS_AGE_HOURS)

    def test_32_unicode_news_source_preserved(self):
        source = "Хабр 🤖 — статьи/обзоры"
        result = _bridge(news_source=source)
        self.assertEqual(result["news"]["source"], source)

    def test_33_negative_and_fractional_age_hours_preserved(self):
        for age in (-2.5, 0.25, 48.0):
            with self.subTest(age=age):
                result = _bridge(news_age_hours=age)
                self.assertEqual(result["news"]["age_hours"], age)


class TestProductBlock(unittest.TestCase):
    def setUp(self):
        self.plan = _make_plan()
        self.result = _bridge(plan=self.plan)
        self.product = self.result["product"]

    def test_34_product_exact_key_set(self):
        self.assertEqual(
            frozenset(self.product.keys()),
            frozenset(
                {
                    "id",
                    "name",
                    "description",
                    "category",
                    "affiliate_link",
                    "free_trial",
                    "status",
                }
            ),
        )

    def test_35_product_id_is_source(self):
        self.assertEqual(self.product["id"], "source")

    def test_36_product_name_equals_topic(self):
        self.assertEqual(self.product["name"], self.plan.topic)

    def test_37_product_description_equals_angle(self):
        self.assertEqual(self.product["description"], self.plan.angle)

    def test_38_product_category_is_source(self):
        self.assertEqual(self.product["category"], "Source")

    def test_39_product_affiliate_link_equals_cta_link(self):
        self.assertEqual(self.product["affiliate_link"], self.plan.cta_link)

    def test_40_product_free_trial_is_false(self):
        self.assertIs(self.product["free_trial"], False)

    def test_41_product_status_is_active(self):
        self.assertEqual(self.product["status"], "active")

    def test_42_is_affiliate_is_false(self):
        self.assertIs(self.result["is_affiliate"], False)


class TestLegacyValidatorCompatibility(unittest.TestCase):
    def test_43_normal_dict_passes_validate_content_plan(self):
        result = _bridge()
        verdict = validate_content_plan(result)
        self.assertIs(verdict["valid"], True)
        self.assertEqual(verdict["issues"], [])


class TestLosslessness(unittest.TestCase):
    def test_44_workflow_format_remains_workflow(self):
        result = _bridge(plan=_make_plan(fmt=ContentFormat.WORKFLOW))
        self.assertEqual(result["format"], "workflow")

    def test_45_comparison_format_remains_comparison(self):
        result = _bridge(plan=_make_plan(fmt=ContentFormat.COMPARISON))
        self.assertEqual(result["format"], "comparison")

    def test_46_breaking_news_remains_breaking_news(self):
        result = _bridge(plan=_make_plan(fmt=ContentFormat.BREAKING_NEWS))
        self.assertEqual(result["format"], "breaking_news")

    def test_47_no_old_russian_format_remapping(self):
        old_labels = (
            "Секретный промпт",
            "Бесплатный аналог",
            "Обход лимитов",
            "Скрытая фича",
            "Лайфхак связка",
            "Топ бесплатных AI",
            "Новость AI",
        )
        for fmt in ContentFormat:
            with self.subTest(format=fmt.value):
                result = _bridge(plan=_make_plan(fmt=fmt))
                self.assertNotIn(result["format"], old_labels)

    def test_48_empty_strategist_owned_strings_preserved(self):
        plan = _make_plan()
        plan = replace(
            plan,
            hook="",
            objective="",
            tone="",
            angle="",
            cta="",
            language="",
            mode="",
        )
        result = _bridge(plan=plan)
        self.assertEqual(result["hook"], "")
        self.assertEqual(result["objective"], "")
        self.assertEqual(result["tone"], "")
        self.assertEqual(result["angle"], "")
        self.assertEqual(result["cta"], "")
        self.assertEqual(result["language"], "")
        self.assertEqual(result["mode"], "")
        self.assertEqual(result["product"]["description"], "")
        self.assertEqual(result["product"]["name"], plan.topic)

    def test_49_empty_cta_link_preserved(self):
        plan = _make_plan()
        plan = replace(plan, cta_link="")
        result = _bridge(plan=plan)
        self.assertEqual(result["cta_link"], "")
        self.assertEqual(result["news"]["url"], "")
        self.assertEqual(result["product"]["affiliate_link"], "")

    def test_50_structure_order_preserved(self):
        structure = ("z_last", "m_middle", "a_first", "b_second", "cta")
        plan = _make_plan()
        plan = replace(plan, structure=structure)
        result = _bridge(plan=plan)
        self.assertEqual(result["structure"], structure)
        self.assertEqual(
            result["structure"],
            ("z_last", "m_middle", "a_first", "b_second", "cta"),
        )

    def test_51_target_platform_input_not_mutated(self):
        platforms = (TargetPlatform.TELEGRAM, TargetPlatform.X)
        plan = _make_plan(platforms=platforms)
        before = repr(platforms)
        _bridge(plan=plan)
        self.assertEqual(repr(platforms), before)

    def test_52_strategist_plan_not_mutated(self):
        plan = _make_plan()
        before = repr(plan)
        _bridge(plan=plan)
        self.assertEqual(repr(plan), before)


class TestRequiredArguments(unittest.TestCase):
    def _signature(self):
        return inspect.signature(
            legacy_bridge.strategist_plan_to_legacy_plan
        )

    def test_53_created_at_required_keyword_only(self):
        param = self._signature().parameters["created_at"]
        self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(param.default, inspect.Parameter.empty)

    def test_54_news_source_required_keyword_only(self):
        param = self._signature().parameters["news_source"]
        self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(param.default, inspect.Parameter.empty)

    def test_55_news_age_hours_required_keyword_only(self):
        param = self._signature().parameters["news_age_hours"]
        self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(param.default, inspect.Parameter.empty)


class TestStructuralBoundaries(unittest.TestCase):
    def _module_source(self) -> str:
        with open(legacy_bridge.__file__, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_56_all_exact(self):
        self.assertEqual(
            legacy_bridge.__all__, ["strategist_plan_to_legacy_plan"]
        )

    def test_57_exactly_one_public_function(self):
        public_functions = [
            name
            for name, obj in vars(legacy_bridge).items()
            if callable(obj)
            and not name.startswith("_")
            and getattr(obj, "__module__", None) == _BRIDGE_MODULE
        ]
        self.assertEqual(
            public_functions, ["strategist_plan_to_legacy_plan"]
        )

    def test_58_only_production_domain_import_is_strategist_plan(self):
        source = self._module_source()
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        self.assertEqual(
            import_lines, ["from src.domain.strategist import StrategistPlan"]
        )

    def test_59_no_old_strategist_or_plan_factory_reference(self):
        source = self._module_source()
        for token in (
            "src.agents.strategist",
            "create_content_plan",
            "agents.strategist",
        ):
            self.assertNotIn(token, source)

    def test_60_no_config_env_filesystem_state_research(self):
        source = self._module_source()
        for token in (
            "Config",
            "environ",
            "getenv",
            "open(",
            "Path(",
            "StateService",
            "src.research",
            "import research",
            "partners",
            "settings",
        ):
            self.assertNotIn(token, source)

    def test_61_no_clock_imports(self):
        source = self._module_source()
        for token in ("random", "datetime", "time"):
            self.assertNotIn(token, source)

    def test_62_no_try_except(self):
        source = self._module_source()
        self.assertNotIn("try", source)

    def test_63_no_format_mapping_table(self):
        source = self._module_source()
        for token in (
            "_FORMAT",
            "FORMAT_MAP",
            "format_map",
            "mapping",
        ):
            self.assertNotIn(token, source)

    def test_64_no_russian_legacy_format_labels_in_bridge(self):
        source = self._module_source()
        for token in (
            "Секретный промпт",
            "Бесплатный аналог",
            "Обход лимитов",
            "Скрытая фича",
            "Лайфхак связка",
            "Топ бесплатных AI",
            "Новость AI",
        ):
            self.assertNotIn(token, source)

    def test_65_no_validation_calls_inside_bridge(self):
        source = self._module_source()
        for token in ("validate_", "is_fallback"):
            self.assertNotIn(token, source)

    def test_66_no_mutation_assignments_to_plan(self):
        source = self._module_source()
        self.assertNotIn("plan.", source.replace("plan", "plan", 1)) if False else None
        for token in (
            "plan.content_format =",
            "plan.content_cluster =",
            "plan.structure =",
            "plan.target_platforms =",
            "setattr(plan",
        ):
            self.assertNotIn(token, source)

    def test_67_no_structure_list_conversion(self):
        source = self._module_source()
        self.assertNotIn("list(", source)

    def test_68_no_platform_sort_dedup_filter(self):
        source = self._module_source()
        for token in ("sorted(", "set(", "filter(", "dedup"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
