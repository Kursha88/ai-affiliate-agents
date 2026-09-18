"""Unit tests for the deterministic Strategist Policy Engine (Step 15D-B).

Covers enrichment correctness per format/cluster, determinism, mutation
freedom, SELECT-field independence, malformed-input errors and the
structural boundaries of ``src/strategy/strategist_policy.py``.
"""

import re
import unittest
from dataclasses import replace

from src.domain.strategy import (
    CandidateScore,
    CandidateStage,
    ContentCandidate,
    ContentCluster,
    ContentFormat,
    DiscoveryCandidate,
    SourceType,
    StrategicSelection,
    TargetPlatform,
    VerificationResult,
    VerificationStatus,
)
from src.domain.strategist import StrategistEnrichment, StrategistInput
from src.strategy import strategist_policy

_UNSET = object()  # sentinel: distinguishes "explicitly None" from "default"

_ENRICHMENT_FIELDS = (
    "angle",
    "hook",
    "objective",
    "cta",
    "cta_link",
    "tone",
    "structure",
    "language",
    "mode",
)


def _make_candidate(
    cluster=ContentCluster.AI_TOOLS,
    selection=_UNSET,
    score=None,
    verification=None,
    content_id=None,
):
    """Smallest real ContentCandidate fixture (defaults = a selected one)."""
    if selection is _UNSET:
        selection = StrategicSelection(
            selected=True,
            selection_reason="default reason",
            recommended_format=ContentFormat.PRACTICAL_GUIDE,
            target_platforms=(TargetPlatform.TELEGRAM,),
        )
    return ContentCandidate(
        candidate=DiscoveryCandidate(
            candidate_id="c-1",
            title="Default Title",
            source_type=SourceType.GITHUB,
            source_url="https://example.com/tool",
            discovered_at="2026-09-18T00:00:00Z",
            content_cluster=cluster,
        ),
        verification=verification if verification is not None else VerificationResult(),
        score=score,
        selection=selection,
        stage=CandidateStage.SELECTED,
        content_id=content_id,
    )


def _make_input(**kwargs):
    return StrategistInput(content_candidate=_make_candidate(**kwargs))


class TestBasicBehavior(unittest.TestCase):
    def test_01_returns_real_strategist_enrichment(self):
        enrichment = strategist_policy.build_strategist_enrichment(_make_input())
        self.assertIsInstance(enrichment, StrategistEnrichment)

    def test_02_deterministic_same_input_equal_output(self):
        first = strategist_policy.build_strategist_enrichment(_make_input())
        second = strategist_policy.build_strategist_enrichment(_make_input())
        self.assertEqual(first, second)

    def test_03_does_not_mutate_strategist_input(self):
        input_obj = _make_input()
        before = repr(input_obj)
        strategist_policy.build_strategist_enrichment(input_obj)
        self.assertEqual(repr(input_obj), before)

    def test_04_does_not_mutate_content_candidate(self):
        candidate = _make_candidate()
        before = repr(candidate)
        strategist_policy.build_strategist_enrichment(
            StrategistInput(content_candidate=candidate)
        )
        self.assertEqual(repr(candidate), before)

    def test_05_does_not_mutate_strategic_selection(self):
        selection = StrategicSelection(
            selected=True,
            selection_reason="reason",
            recommended_format=ContentFormat.WORKFLOW,
            target_platforms=(TargetPlatform.X,),
        )
        before = repr(selection)
        candidate = _make_candidate(selection=selection)
        strategist_policy.build_strategist_enrichment(
            StrategistInput(content_candidate=candidate)
        )
        self.assertEqual(repr(selection), before)


class TestFormatCoverage(unittest.TestCase):
    def _enrichment_for_format(self, fmt):
        selection = StrategicSelection(
            selected=True,
            selection_reason="reason",
            recommended_format=fmt,
            target_platforms=(TargetPlatform.TELEGRAM,),
        )
        return strategist_policy.build_strategist_enrichment(
            _make_input(selection=selection)
        )

    def test_06_10_exact_format_policies(self):
        expected = {
            ContentFormat.BREAKING_NEWS: (
                "Быстро объяснить, что произошло и почему это важно",
                "оперативный и фактический",
                ("hook", "what_happened", "why_it_matters", "takeaway", "cta"),
                "Проверить первоисточник",
            ),
            ContentFormat.TOOL_DISCOVERY: (
                "Показать, зачем нужен инструмент и где он полезен",
                "практичный и конкретный",
                ("problem", "tool", "key_features", "use_case", "cta"),
                "Изучить инструмент",
            ),
            ContentFormat.PRACTICAL_GUIDE: (
                "Научить выполнить конкретную задачу шаг за шагом",
                "обучающий и практичный",
                ("hook", "prerequisites", "steps", "result", "cta"),
                "Повторить шаги",
            ),
            ContentFormat.COMPARISON: (
                "Помочь сравнить варианты и понять их различия",
                "аналитический и нейтральный",
                (
                    "context",
                    "option_a",
                    "option_b",
                    "tradeoffs",
                    "recommendation",
                    "cta",
                ),
                "Сравнить варианты",
            ),
            ContentFormat.EXPERIMENT: (
                "Проверить гипотезу на практическом эксперименте",
                "исследовательский и прозрачный",
                ("hypothesis", "setup", "test", "result", "takeaway", "cta"),
                "Повторить эксперимент",
            ),
            ContentFormat.WORKFLOW: (
                "Показать повторяемый рабочий процесс от задачи до результата",
                "системный и практичный",
                ("problem", "workflow", "steps", "result", "cta"),
                "Попробовать этот процесс",
            ),
            ContentFormat.PROMPT: (
                "Дать готовый способ решить задачу с помощью промта",
                "прикладной и понятный",
                ("problem", "prompt", "how_to_use", "expected_result", "cta"),
                "Попробовать промт",
            ),
            ContentFormat.CASE_STUDY: (
                "Разобрать реальный кейс, результат и практические выводы",
                "аналитический и прикладной",
                ("context", "approach", "result", "lessons", "cta"),
                "Применить выводы",
            ),
            ContentFormat.OPINION_ANALYSIS: (
                "Разобрать позицию через аргументы, факты и контраргументы",
                "аналитический и взвешенный",
                ("thesis", "evidence", "counterpoint", "conclusion", "cta"),
                "Изучить аргументы",
            ),
            ContentFormat.ROUNDUP: (
                "Собрать несколько полезных вариантов и показать различия между ними",
                "обзорный и практичный",
                ("intro", "items", "differences", "recommendation", "cta"),
                "Изучить подборку",
            ),
        }
        for fmt, (objective, tone, structure, cta) in expected.items():
            with self.subTest(format=fmt.value):
                enrichment = self._enrichment_for_format(fmt)
                self.assertEqual(enrichment.objective, objective)
                self.assertEqual(enrichment.tone, tone)
                self.assertEqual(enrichment.structure, structure)
                self.assertEqual(enrichment.cta, cta)

    def test_10_every_content_format_member_present_in_policy_mapping(self):
        for fmt in ContentFormat:
            with self.subTest(format=fmt.value):
                self.assertIn(fmt, strategist_policy._FORMAT_POLICIES)

    def test_11_policy_mapping_has_no_extra_keys(self):
        self.assertEqual(
            frozenset(strategist_policy._FORMAT_POLICIES), frozenset(ContentFormat)
        )


class TestClusterCoverage(unittest.TestCase):
    EXPECTED_ANGLES = {
        ContentCluster.VIBE_CODING: "Как это меняет практический процесс разработки",
        ContentCluster.AI_AGENTS: "Как использовать AI-агентов для выполнения реальных задач",
        ContentCluster.AI_TOOLS: "Как инструмент решает конкретную практическую проблему",
        ContentCluster.AUTOMATION: "Как автоматизировать повторяемую работу и сократить ручные действия",
        ContentCluster.FREE_AI: "Что можно получить бесплатно и какие есть ограничения",
        ContentCluster.PRACTICAL_EXPERIMENTS: "Что происходит при практической проверке идеи",
        ContentCluster.AI_NEWS: "Что изменилось и какое практическое значение это имеет",
    }

    def test_12_all_cluster_angles_exact(self):
        for cluster, angle in self.EXPECTED_ANGLES.items():
            with self.subTest(cluster=cluster.value):
                selection = StrategicSelection(
                    selected=True,
                    selection_reason="reason",
                    recommended_format=ContentFormat.PRACTICAL_GUIDE,
                    target_platforms=(TargetPlatform.TELEGRAM,),
                )
                enrichment = strategist_policy.build_strategist_enrichment(
                    _make_input(cluster=cluster, selection=selection)
                )
                self.assertEqual(enrichment.angle, angle)

    def test_13_every_content_cluster_member_present_in_angle_mapping(self):
        for cluster in ContentCluster:
            with self.subTest(cluster=cluster.value):
                self.assertIn(cluster, strategist_policy._CLUSTER_ANGLES)

    def test_14_angle_mapping_has_no_extra_keys(self):
        self.assertEqual(
            frozenset(strategist_policy._CLUSTER_ANGLES), frozenset(ContentCluster)
        )


class TestHookAndLink(unittest.TestCase):
    def _input_with(self, title, source_url):
        candidate = _make_candidate()
        base = candidate.candidate
        candidate = replace(
            candidate,
            candidate=replace(base, title=title, source_url=source_url),
        )
        return StrategistInput(content_candidate=candidate)

    def test_15_hook_equals_title_exactly(self):
        enrichment = strategist_policy.build_strategist_enrichment(
            self._input_with("Some Title", "https://example.com/a")
        )
        self.assertEqual(enrichment.hook, "Some Title")

    def test_16_unicode_title_preserved_exactly(self):
        title = "Заголовок: тест — «кавычки», emoji 🚀"
        enrichment = strategist_policy.build_strategist_enrichment(
            self._input_with(title, "https://example.com/a")
        )
        self.assertEqual(enrichment.hook, title)

    def test_17_whitespace_in_title_preserved_exactly(self):
        title = "  Title\twith   spaces\nand newline  "
        enrichment = strategist_policy.build_strategist_enrichment(
            self._input_with(title, "https://example.com/a")
        )
        self.assertEqual(enrichment.hook, title)

    def test_18_cta_link_equals_source_url_exactly(self):
        enrichment = strategist_policy.build_strategist_enrichment(
            self._input_with("Title", "https://example.com/page")
        )
        self.assertEqual(enrichment.cta_link, "https://example.com/page")

    def test_19_empty_source_url_preserved_exactly(self):
        enrichment = strategist_policy.build_strategist_enrichment(
            self._input_with("Title", "")
        )
        self.assertEqual(enrichment.cta_link, "")

    def test_20_source_url_query_and_fragment_preserved_exactly(self):
        url = "https://example.com/p?a=1&b=%20x#frag-ment"
        enrichment = strategist_policy.build_strategist_enrichment(
            self._input_with("Title", url)
        )
        self.assertEqual(enrichment.cta_link, url)


class TestConstants(unittest.TestCase):
    def test_21_language_is_ru(self):
        enrichment = strategist_policy.build_strategist_enrichment(_make_input())
        self.assertEqual(enrichment.language, "ru")

    def test_22_mode_is_growth(self):
        enrichment = strategist_policy.build_strategist_enrichment(_make_input())
        self.assertEqual(enrichment.mode, "growth")


class TestSeparationOfResponsibilities(unittest.TestCase):
    def _enrichment(self, **kwargs):
        return strategist_policy.build_strategist_enrichment(_make_input(**kwargs))

    def test_23_changing_cluster_changes_angle_only(self):
        selection = StrategicSelection(
            selected=True,
            selection_reason="reason",
            recommended_format=ContentFormat.PRACTICAL_GUIDE,
            target_platforms=(TargetPlatform.TELEGRAM,),
        )
        base = self._enrichment(
            cluster=ContentCluster.AI_TOOLS, selection=selection
        )
        for cluster in ContentCluster:
            if cluster is ContentCluster.AI_TOOLS:
                continue
            with self.subTest(cluster=cluster.value):
                other = self._enrichment(cluster=cluster, selection=selection)
                self.assertNotEqual(other.angle, base.angle)
                for field_name in _ENRICHMENT_FIELDS:
                    if field_name != "angle":
                        self.assertEqual(
                            getattr(other, field_name), getattr(base, field_name)
                        )

    def test_24_changing_format_changes_format_fields_angle_constant(self):
        cluster = ContentCluster.AI_TOOLS
        base = self._enrichment(
            cluster=cluster,
            selection=StrategicSelection(
                selected=True,
                selection_reason="reason",
                recommended_format=ContentFormat.PRACTICAL_GUIDE,
                target_platforms=(TargetPlatform.TELEGRAM,),
            ),
        )
        format_owned = ("objective", "tone", "structure", "cta")
        seen = set()
        for fmt in ContentFormat:
            if fmt is ContentFormat.PRACTICAL_GUIDE:
                continue
            with self.subTest(format=fmt.value):
                other = self._enrichment(
                    cluster=cluster,
                    selection=StrategicSelection(
                        selected=True,
                        selection_reason="reason",
                        recommended_format=fmt,
                        target_platforms=(TargetPlatform.TELEGRAM,),
                    ),
                )
                self.assertEqual(other.angle, base.angle)
                self.assertEqual(other.hook, base.hook)
                self.assertEqual(other.cta_link, base.cta_link)
                self.assertEqual(other.language, base.language)
                self.assertEqual(other.mode, base.mode)
                for field_name in format_owned:
                    self.assertNotEqual(
                        getattr(other, field_name), getattr(base, field_name)
                    )
                seen.add(
                    (other.objective, other.tone, other.structure, other.cta)
                )
        # Every non-base format yields a distinct policy quadruple.
        self.assertEqual(len(seen), len(ContentFormat) - 1)

    def test_25_research_required_does_not_affect_enrichment(self):
        false_sel = StrategicSelection(
            selected=True,
            selection_reason="reason",
            recommended_format=ContentFormat.WORKFLOW,
            target_platforms=(TargetPlatform.TELEGRAM,),
            research_required=False,
        )
        true_sel = replace(false_sel, research_required=True)
        self.assertEqual(
            self._enrichment(selection=false_sel),
            self._enrichment(selection=true_sel),
        )

    def test_26_experiment_required_does_not_affect_enrichment(self):
        false_sel = StrategicSelection(
            selected=True,
            selection_reason="reason",
            recommended_format=ContentFormat.WORKFLOW,
            target_platforms=(TargetPlatform.TELEGRAM,),
            experiment_required=False,
        )
        true_sel = replace(false_sel, experiment_required=True)
        self.assertEqual(
            self._enrichment(selection=false_sel),
            self._enrichment(selection=true_sel),
        )

    def test_27_target_platforms_differences_do_not_affect_enrichment(self):
        sel_a = StrategicSelection(
            selected=True,
            selection_reason="reason",
            recommended_format=ContentFormat.WORKFLOW,
            target_platforms=(TargetPlatform.TELEGRAM,),
        )
        sel_b = StrategicSelection(
            selected=True,
            selection_reason="reason",
            recommended_format=ContentFormat.WORKFLOW,
            target_platforms=(
                TargetPlatform.X,
                TargetPlatform.LINKEDIN,
                TargetPlatform.YOUTUBE_SHORTS,
            ),
        )
        self.assertEqual(
            self._enrichment(selection=sel_a), self._enrichment(selection=sel_b)
        )

    def test_28_selection_reason_differences_do_not_affect_enrichment(self):
        sel_a = StrategicSelection(
            selected=True,
            selection_reason="reason A",
            recommended_format=ContentFormat.WORKFLOW,
            target_platforms=(TargetPlatform.TELEGRAM,),
        )
        sel_b = replace(sel_a, selection_reason="totally different reason")
        self.assertEqual(
            self._enrichment(selection=sel_a), self._enrichment(selection=sel_b)
        )

    def test_29_score_differences_do_not_affect_enrichment(self):
        score_a = CandidateScore(
            novelty=1.0,
            practical_utility=2.0,
            free_availability=3.0,
            audience_interest=4.0,
            viral_potential=5.0,
            credibility=6.0,
        )
        score_b = CandidateScore(
            novelty=9.0,
            practical_utility=8.0,
            free_availability=7.0,
            audience_interest=6.0,
            viral_potential=5.0,
            credibility=4.0,
        )
        self.assertEqual(
            self._enrichment(score=score_a), self._enrichment(score=score_b)
        )

    def test_30_verification_differences_do_not_affect_enrichment(self):
        ver_a = VerificationResult()
        ver_b = VerificationResult(
            verification_status=VerificationStatus.VERIFIED,
            primary_source_found=True,
            primary_source_url="https://example.com/primary",
            confidence=0.95,
            notes="verified",
        )
        self.assertEqual(
            self._enrichment(verification=ver_a),
            self._enrichment(verification=ver_b),
        )

    def test_31_content_id_differences_do_not_affect_enrichment(self):
        self.assertEqual(
            self._enrichment(content_id=None),
            self._enrichment(content_id="content-123"),
        )


class TestMalformedInput(unittest.TestCase):
    def test_32_missing_selection_raises_exact_message(self):
        candidate = _make_candidate(selection=None)
        with self.assertRaises(ValueError) as ctx:
            strategist_policy.build_strategist_enrichment(
                StrategistInput(content_candidate=candidate)
            )
        self.assertEqual(
            str(ctx.exception), "strategist input missing strategic selection"
        )

    def test_33_missing_recommended_format_raises_exact_message(self):
        selection = StrategicSelection(
            selected=True,
            selection_reason="reason",
            recommended_format=None,
            target_platforms=(TargetPlatform.TELEGRAM,),
        )
        candidate = _make_candidate(selection=selection)
        with self.assertRaises(ValueError) as ctx:
            strategist_policy.build_strategist_enrichment(
                StrategistInput(content_candidate=candidate)
            )
        self.assertEqual(
            str(ctx.exception), "strategist input missing recommended format"
        )

    def test_34_missing_content_cluster_raises_exact_message(self):
        candidate = _make_candidate()
        candidate = replace(
            candidate,
            candidate=replace(candidate.candidate, content_cluster=None),
        )
        with self.assertRaises(ValueError) as ctx:
            strategist_policy.build_strategist_enrichment(
                StrategistInput(content_candidate=candidate)
            )
        self.assertEqual(
            str(ctx.exception), "strategist input missing content cluster"
        )

    def test_35_validation_order_missing_selection_beats_missing_cluster(self):
        candidate = _make_candidate()
        candidate = replace(
            candidate,
            selection=None,
            candidate=replace(candidate.candidate, content_cluster=None),
        )
        with self.assertRaises(ValueError) as ctx:
            strategist_policy.build_strategist_enrichment(
                StrategistInput(content_candidate=candidate)
            )
        self.assertEqual(
            str(ctx.exception), "strategist input missing strategic selection"
        )

    def test_36_validation_order_missing_format_beats_missing_cluster(self):
        selection = StrategicSelection(
            selected=True,
            selection_reason="reason",
            recommended_format=None,
            target_platforms=(TargetPlatform.TELEGRAM,),
        )
        candidate = _make_candidate(selection=selection)
        candidate = replace(
            candidate,
            candidate=replace(candidate.candidate, content_cluster=None),
        )
        with self.assertRaises(ValueError) as ctx:
            strategist_policy.build_strategist_enrichment(
                StrategistInput(content_candidate=candidate)
            )
        self.assertEqual(
            str(ctx.exception), "strategist input missing recommended format"
        )


class _FakeFormat:
    """Test-only stand-in for an unsupported ContentFormat value."""

    def __repr__(self) -> str:  # pragma: no cover - defensive clarity only
        return "not-a-real-format"


class _FakeCluster:
    """Test-only stand-in for an unsupported ContentCluster value."""

    def __repr__(self) -> str:  # pragma: no cover - defensive clarity only
        return "not-a-real-cluster"


class TestUnsupportedValues(unittest.TestCase):
    def test_37_unsupported_format_raises_exact_message(self):
        selection = StrategicSelection(
            selected=True,
            selection_reason="reason",
            recommended_format=None,
            target_platforms=(TargetPlatform.TELEGRAM,),
        )
        # Frozen real enums cannot hold fake members; bypass the None check
        # via a subclass-free proxy object exposing only the read attributes.
        candidate = _make_candidate(selection=selection)
        proxy_candidate = replace(
            candidate,
            selection=replace(selection, recommended_format=_FakeFormat()),
        )
        input_obj = StrategistInput(content_candidate=proxy_candidate)
        with self.assertRaises(ValueError) as ctx:
            strategist_policy.build_strategist_enrichment(input_obj)
        self.assertEqual(str(ctx.exception), "unsupported content format")

    def test_38_unsupported_cluster_raises_exact_message(self):
        candidate = _make_candidate()
        proxy_candidate = replace(
            candidate,
            candidate=replace(candidate.candidate, content_cluster=_FakeCluster()),
        )
        input_obj = StrategistInput(content_candidate=proxy_candidate)
        with self.assertRaises(ValueError) as ctx:
            strategist_policy.build_strategist_enrichment(input_obj)
        self.assertEqual(str(ctx.exception), "unsupported content cluster")


class TestStructuralBoundaries(unittest.TestCase):
    def _module_source(self) -> str:
        with open(strategist_policy.__file__, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_39_all_exact(self):
        self.assertEqual(strategist_policy.__all__, ["build_strategist_enrichment"])

    def test_40_exactly_one_public_function(self):
        public_functions = [
            name
            for name, obj in vars(strategist_policy).items()
            if callable(obj)
            and not name.startswith("_")
            and getattr(obj, "__module__", None) == "src.strategy.strategist_policy"
        ]
        self.assertEqual(public_functions, ["build_strategist_enrichment"])

    def test_41_enrichment_constructed_exactly_once_per_call(self):
        original = StrategistEnrichment.__init__
        calls = []

        def counting_init(self, *args, **kwargs):
            calls.append((args, kwargs))
            return original(self, *args, **kwargs)

        try:
            StrategistEnrichment.__init__ = counting_init
            strategist_policy.build_strategist_enrichment(_make_input())
        finally:
            StrategistEnrichment.__init__ = original
        self.assertEqual(len(calls), 1)

    def test_42_no_strategist_plan_reference(self):
        source = self._module_source()
        self.assertNotIn("StrategistPlan", source)

    def test_43_no_build_strategist_plan_reference(self):
        source = self._module_source()
        self.assertNotIn("build_strategist_plan", source)

    def test_44_no_build_strategist_input_call_or_import(self):
        source = self._module_source()
        self.assertNotIn("build_strategist_input", source)

    def test_45_no_forbidden_stdlib_imports(self):
        source = self._module_source()
        for token in ("random", "datetime", "os", "pathlib", "yaml", "requests"):
            self.assertNotIn(token, source)

    def test_46_no_config_or_main_or_agents_imports(self):
        source = self._module_source()
        for token in ("Config", "src.main", "src.agents"):
            self.assertNotIn(token, source)

    def test_47_no_validators_state_or_research_imports(self):
        source = self._module_source()
        for token in (
            "validators",
            "StateService",
            "research",
            "state",
        ):
            self.assertNotIn(token, source)

    def test_48_no_try_except(self):
        source = self._module_source()
        self.assertNotIn("try", source)

    def test_49_no_filesystem_environment_network_calls(self):
        source = self._module_source()
        for token in (
            "open(",
            "environ",
            "getenv",
            "requests.",
            "urllib",
            "socket",
            "Path(",
        ):
            self.assertNotIn(token, source)

    def test_50_no_target_platforms_read(self):
        source = self._module_source()
        self.assertNotIn("target_platforms", source)

    def test_51_no_research_required_read(self):
        source = self._module_source()
        self.assertNotIn("research_required", source)

    def test_52_no_experiment_required_read(self):
        source = self._module_source()
        self.assertNotIn("experiment_required", source)

    def test_53_no_selection_reason_read(self):
        source = self._module_source()
        self.assertNotIn("selection_reason", source)

    def test_54_no_score_verification_content_id_reads(self):
        source = self._module_source()
        for token in ("score", "verification", "content_id"):
            self.assertNotIn(token, source)

    def test_55_no_discovery_extra_field_reads(self):
        source = self._module_source()
        for token in (
            "source_type",
            "summary",
            "metadata",
            "raw_score",
            "published_at",
            "discovered_at",
        ):
            self.assertNotIn(token, source)

    def test_56_only_permitted_discovery_reads_in_code(self):
        # Title, content_cluster and source_url are the only DiscoveryCandidate
        # attributes the module may touch; verify each attribute access is one
        # of the permitted ones.
        source = self._module_source()
        accesses = set(re.findall(r"candidate\.candidate\.(\w+)", source))
        self.assertEqual(accesses, {"content_cluster", "title", "source_url"})

    def test_57_mapping_keys_are_enum_members(self):
        for key in strategist_policy._FORMAT_POLICIES:
            self.assertIsInstance(key, ContentFormat)
        for key in strategist_policy._CLUSTER_ANGLES:
            self.assertIsInstance(key, ContentCluster)

    def test_58_mapping_values_immutable_structure_tuples(self):
        for policy in strategist_policy._FORMAT_POLICIES.values():
            objective, tone, structure, cta = policy
            self.assertIsInstance(objective, str)
            self.assertIsInstance(tone, str)
            self.assertIsInstance(structure, tuple)
            self.assertTrue(all(isinstance(step, str) for step in structure))
            self.assertIsInstance(cta, str)
        for angle in strategist_policy._CLUSTER_ANGLES.values():
            self.assertIsInstance(angle, str)

    def test_59_no_fallback_dict_get_for_policy(self):
        source = self._module_source()
        self.assertNotIn(".get(", source)

    def test_60_no_generic_fallback_match_branch(self):
        source = self._module_source()
        self.assertNotIn("case _", source)
        self.assertNotIn("match ", source)


if __name__ == "__main__":
    unittest.main()
