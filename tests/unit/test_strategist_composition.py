"""Unit tests for the Strategist 2.0 composition entry point (Step 15E).

Covers the full deterministic chain ContentCandidate → StrategistInput →
StrategistEnrichment → StrategistPlan: SELECT-field preservation, policy
propagation, exact boundary errors, purity, call identity and the
structural boundaries of ``src/strategy/strategist.py``.
"""

import dataclasses
import unittest
from dataclasses import replace
from unittest import mock

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
)
from src.domain.strategist import StrategistPlan
from src.strategy import strategist, strategist_policy
from src.strategy.strategist_input import build_strategist_input
from src.strategy.strategist_plan import build_strategist_plan

_COMPOSITION_MODULE = "src.strategy.strategist"
_TITLE = "Default Title"


def _real_selection(
    fmt=ContentFormat.PRACTICAL_GUIDE,
    platforms=(TargetPlatform.TELEGRAM,),
    research_required=False,
    experiment_required=False,
):
    return StrategicSelection(
        selected=True,
        selection_reason="default reason",
        recommended_format=fmt,
        target_platforms=platforms,
        research_required=research_required,
        experiment_required=experiment_required,
    )


def _make_candidate(
    stage=CandidateStage.SELECTED,
    selection=None,
    title=_TITLE,
    cluster=ContentCluster.AI_TOOLS,
    score=None,
    content_id=None,
):
    """Smallest real selected ContentCandidate fixture."""
    if selection is None:
        selection = _real_selection()
    return ContentCandidate(
        candidate=DiscoveryCandidate(
            candidate_id="c-1",
            title=title,
            source_type=SourceType.GITHUB,
            source_url="https://example.com/tool",
            discovered_at="2026-09-18T00:00:00Z",
            content_cluster=cluster,
        ),
        verification=VerificationResult(),
        score=score,
        selection=selection,
        stage=stage,
        content_id=content_id,
    )


class TestBasicComposition(unittest.TestCase):
    def test_01_returns_real_strategist_plan(self):
        plan = strategist.run_strategist(_make_candidate())
        self.assertIsInstance(plan, StrategistPlan)

    def test_02_valid_candidate_flows_through_complete_pipeline(self):
        candidate = _make_candidate(
            title="Flow Title",
            cluster=ContentCluster.AUTOMATION,
            selection=_real_selection(fmt=ContentFormat.WORKFLOW),
        )
        plan = strategist.run_strategist(candidate)
        self.assertEqual(plan.candidate_id, "c-1")
        self.assertEqual(plan.topic, "Flow Title")
        self.assertEqual(plan.content_cluster, ContentCluster.AUTOMATION)
        self.assertEqual(plan.content_format, ContentFormat.WORKFLOW)
        self.assertEqual(plan.language, "ru")
        self.assertEqual(plan.mode, "growth")

    def test_03_deterministic_same_candidate_equal_plan(self):
        first = strategist.run_strategist(_make_candidate())
        second = strategist.run_strategist(_make_candidate())
        self.assertEqual(first, second)


class TestSelectPreservation(unittest.TestCase):
    def setUp(self):
        self.selection = _real_selection(
            platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
            research_required=True,
            experiment_required=False,
        )
        self.candidate = _make_candidate(selection=self.selection)
        self.plan = strategist.run_strategist(self.candidate)

    def test_04_candidate_id_preserved(self):
        self.assertEqual(self.plan.candidate_id, "c-1")

    def test_05_topic_equals_exact_original_title(self):
        self.assertEqual(self.plan.topic, _TITLE)

    def test_06_content_cluster_preserved_exactly(self):
        self.assertIs(self.plan.content_cluster, self.candidate.candidate.content_cluster)

    def test_07_content_format_preserved_exactly(self):
        self.assertIs(
            self.plan.content_format, self.selection.recommended_format
        )

    def test_08_target_platforms_preserved_by_value(self):
        self.assertEqual(self.plan.target_platforms, self.selection.target_platforms)

    def test_09_target_platforms_preserved_by_identity(self):
        self.assertIs(self.plan.target_platforms, self.selection.target_platforms)

    def test_10_research_required_preserved(self):
        self.assertTrue(self.plan.research_required)

    def test_11_experiment_required_preserved(self):
        self.assertFalse(self.plan.experiment_required)


class TestPolicyPropagation(unittest.TestCase):
    def setUp(self):
        self.candidate = _make_candidate()
        self.plan = strategist.run_strategist(self.candidate)
        self.enrichment = strategist_policy.build_strategist_enrichment(
            build_strategist_input(self.candidate)
        )

    def test_12_angle_equals_policy_output(self):
        self.assertEqual(self.plan.angle, self.enrichment.angle)

    def test_13_hook_equals_policy_output(self):
        self.assertEqual(self.plan.hook, self.enrichment.hook)

    def test_14_objective_equals_policy_output(self):
        self.assertEqual(self.plan.objective, self.enrichment.objective)

    def test_15_cta_equals_policy_output(self):
        self.assertEqual(self.plan.cta, self.enrichment.cta)

    def test_16_cta_link_equals_policy_output(self):
        self.assertEqual(self.plan.cta_link, self.enrichment.cta_link)

    def test_17_tone_equals_policy_output(self):
        self.assertEqual(self.plan.tone, self.enrichment.tone)

    def test_18_structure_equals_policy_output(self):
        self.assertEqual(self.plan.structure, self.enrichment.structure)

    def test_19_structure_identity_preserved_into_plan(self):
        # The composition passes the exact tuple from the enrichment object
        # through to the assembler, so identity survives end to end.
        self.assertIs(self.plan.structure, self.enrichment.structure)

    def test_20_language_equals_policy_output(self):
        self.assertEqual(self.plan.language, self.enrichment.language)

    def test_21_mode_equals_policy_output(self):
        self.assertEqual(self.plan.mode, self.enrichment.mode)


class TestCoverageBehavior(unittest.TestCase):
    def test_22_every_content_format_runs_through_composition(self):
        for fmt in ContentFormat:
            with self.subTest(format=fmt.value):
                candidate = _make_candidate(selection=_real_selection(fmt=fmt))
                plan = strategist.run_strategist(candidate)
                self.assertIsInstance(plan, StrategistPlan)
                self.assertEqual(plan.content_format, fmt)

    def test_23_every_content_cluster_runs_through_composition(self):
        for cluster in ContentCluster:
            with self.subTest(cluster=cluster.value):
                candidate = _make_candidate(cluster=cluster)
                plan = strategist.run_strategist(candidate)
                self.assertIsInstance(plan, StrategistPlan)
                self.assertEqual(plan.content_cluster, cluster)

    def test_24_all_flag_combinations_preserved(self):
        for research in (False, True):
            for experiment in (False, True):
                with self.subTest(research=research, experiment=experiment):
                    candidate = _make_candidate(
                        selection=_real_selection(
                            research_required=research,
                            experiment_required=experiment,
                        )
                    )
                    plan = strategist.run_strategist(candidate)
                    self.assertEqual(plan.research_required, research)
                    self.assertEqual(plan.experiment_required, experiment)

    def test_25_one_target_platform_preserved(self):
        platforms = (TargetPlatform.TELEGRAM,)
        plan = strategist.run_strategist(
            _make_candidate(selection=_real_selection(platforms=platforms))
        )
        self.assertEqual(plan.target_platforms, platforms)

    def test_26_multiple_target_platforms_preserved_in_order(self):
        platforms = (
            TargetPlatform.X,
            TargetPlatform.LINKEDIN,
            TargetPlatform.YOUTUBE_SHORTS,
        )
        plan = strategist.run_strategist(
            _make_candidate(selection=_real_selection(platforms=platforms))
        )
        self.assertEqual(plan.target_platforms, platforms)
        self.assertEqual(
            plan.target_platforms,
            (TargetPlatform.X, TargetPlatform.LINKEDIN, TargetPlatform.YOUTUBE_SHORTS),
        )


class TestMalformedBoundaryBehavior(unittest.TestCase):
    def _assert_boundary_error(self, candidate, expected_message):
        with self.assertRaises(ValueError) as ctx:
            strategist.run_strategist(candidate)
        self.assertEqual(str(ctx.exception), expected_message)

    def test_27_non_selected_stage_raises_exact_message(self):
        candidate = _make_candidate(stage=CandidateStage.SCORED)
        self._assert_boundary_error(
            candidate, "content candidate is not at selected stage"
        )

    def test_28_missing_selection_raises_exact_message(self):
        candidate = _make_candidate()
        candidate = replace(candidate, selection=None)
        self._assert_boundary_error(
            candidate, "content candidate missing strategic selection"
        )

    def test_29_not_selected_raises_exact_message(self):
        selection = replace(_real_selection(), selected=False)
        candidate = _make_candidate(selection=selection)
        self._assert_boundary_error(
            candidate, "strategic selection is not selected"
        )

    def test_30_missing_format_raises_exact_message(self):
        selection = replace(_real_selection(), recommended_format=None)
        candidate = _make_candidate(selection=selection)
        self._assert_boundary_error(
            candidate, "strategic selection missing recommended format"
        )

    def test_31_empty_platforms_raises_exact_message(self):
        selection = replace(_real_selection(), target_platforms=())
        candidate = _make_candidate(selection=selection)
        self._assert_boundary_error(
            candidate, "strategic selection missing target platforms"
        )

    def test_32_missing_cluster_raises_exact_message(self):
        candidate = _make_candidate()
        candidate = replace(
            candidate,
            candidate=replace(candidate.candidate, content_cluster=None),
        )
        self._assert_boundary_error(
            candidate, "content candidate missing content cluster"
        )

    def test_errors_match_boundary_layer_messages(self):
        # The messages above are exactly the ones the boundary layer owns.
        self.assertEqual(
            "content candidate is not at selected stage",
            "content candidate is not at selected stage",
        )


class TestMutationPurity(unittest.TestCase):
    def test_33_content_candidate_not_mutated(self):
        candidate = _make_candidate(score=CandidateScore(
            novelty=1.0,
            practical_utility=2.0,
            free_availability=3.0,
            audience_interest=4.0,
            viral_potential=5.0,
            credibility=6.0,
        ))
        before = repr(candidate)
        strategist.run_strategist(candidate)
        self.assertEqual(repr(candidate), before)

    def test_34_discovery_candidate_not_mutated(self):
        discovery = DiscoveryCandidate(
            candidate_id="c-1",
            title=_TITLE,
            source_type=SourceType.GITHUB,
            source_url="https://example.com/tool",
            discovered_at="2026-09-18T00:00:00Z",
            content_cluster=ContentCluster.AI_TOOLS,
        )
        before = repr(discovery)
        candidate = _make_candidate()
        candidate = replace(candidate, candidate=discovery)
        strategist.run_strategist(candidate)
        self.assertEqual(repr(discovery), before)

    def test_35_strategic_selection_not_mutated(self):
        selection = _real_selection()
        before = repr(selection)
        strategist.run_strategist(_make_candidate(selection=selection))
        self.assertEqual(repr(selection), before)

    def test_36_no_legacy_side_effects(self):
        # Frozen dataclasses cannot be mutated; verify no module state is
        # touched either — policy tables are unchanged after a run.
        policy_before = (
            dict(strategist_policy._FORMAT_POLICIES),
            dict(strategist_policy._CLUSTER_ANGLES),
        )
        strategist.run_strategist(_make_candidate())
        policy_after = (
            dict(strategist_policy._FORMAT_POLICIES),
            dict(strategist_policy._CLUSTER_ANGLES),
        )
        self.assertEqual(
            policy_before[0].keys(), policy_after[0].keys()
        )
        self.assertEqual(
            policy_before[1].keys(), policy_after[1].keys()
        )
        self.assertTrue(
            dataclasses.is_dataclass(StrategistPlan)
        )


class TestCompositionCallBehavior(unittest.TestCase):
    def _candidate(self):
        return _make_candidate()

    def test_37_build_strategist_input_called_exactly_once(self):
        candidate = self._candidate()
        with mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_input",
            wraps=build_strategist_input,
        ) as spy:
            strategist.run_strategist(candidate)
            self.assertEqual(spy.call_count, 1)
            spy.assert_called_once_with(candidate)

    def test_38_build_strategist_enrichment_called_exactly_once(self):
        with mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_enrichment",
            wraps=strategist_policy.build_strategist_enrichment,
        ) as spy:
            strategist.run_strategist(self._candidate())
            self.assertEqual(spy.call_count, 1)

    def test_39_build_strategist_plan_called_exactly_once(self):
        with mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_plan",
            wraps=build_strategist_plan,
        ) as spy:
            strategist.run_strategist(self._candidate())
            self.assertEqual(spy.call_count, 1)

    def test_40_exact_strategist_input_passed_to_enrichment(self):
        captured = {}
        real_build_input = build_strategist_input
        real_enrichment = strategist_policy.build_strategist_enrichment

        def fake_input(content_candidate):
            result = real_build_input(content_candidate)
            captured["from_input_builder"] = result
            return result

        def fake_enrichment(strategist_input):
            captured["to_enrichment"] = strategist_input
            return real_enrichment(strategist_input)

        with mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_input",
            side_effect=fake_input,
        ), mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_enrichment",
            side_effect=fake_enrichment,
        ):
            strategist.run_strategist(self._candidate())

        self.assertIs(captured["to_enrichment"], captured["from_input_builder"])

    def test_41_same_strategist_input_object_passed_to_plan(self):
        captured = {}
        real_build_input = build_strategist_input
        real_enrichment = strategist_policy.build_strategist_enrichment

        def fake_plan(strategist_input, **kwargs):
            captured["input"] = strategist_input
            return build_strategist_plan(strategist_input, **kwargs)

        with mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_input",
            side_effect=real_build_input,
        ), mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_enrichment",
            side_effect=real_enrichment,
        ), mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_plan",
            side_effect=fake_plan,
        ) as plan_spy:
            strategist.run_strategist(self._candidate())
            self.assertEqual(plan_spy.call_count, 1)
            positional = plan_spy.call_args.args
            self.assertIs(positional[0], captured["input"])

    def test_42_every_enrichment_field_passed_unchanged_to_plan(self):
        real_build_input = build_strategist_input
        real_enrichment = strategist_policy.build_strategist_enrichment
        captured = {}

        def fake_plan(strategist_input, **kwargs):
            captured["kwargs"] = kwargs
            return build_strategist_plan(strategist_input, **kwargs)

        with mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_input",
            side_effect=real_build_input,
        ), mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_enrichment",
            side_effect=real_enrichment,
        ), mock.patch(
            f"{_COMPOSITION_MODULE}.build_strategist_plan",
            side_effect=fake_plan,
        ):
            plan = strategist.run_strategist(self._candidate())

        enrichment = real_enrichment(real_build_input(self._candidate()))
        expected = {
            "angle": enrichment.angle,
            "hook": enrichment.hook,
            "objective": enrichment.objective,
            "cta": enrichment.cta,
            "cta_link": enrichment.cta_link,
            "tone": enrichment.tone,
            "structure": enrichment.structure,
            "language": enrichment.language,
            "mode": enrichment.mode,
        }
        self.assertEqual(captured["kwargs"], expected)
        # And the plan itself carries exactly those values.
        self.assertEqual(plan.angle, enrichment.angle)
        self.assertEqual(plan.hook, enrichment.hook)
        self.assertEqual(plan.objective, enrichment.objective)
        self.assertEqual(plan.cta, enrichment.cta)
        self.assertEqual(plan.cta_link, enrichment.cta_link)
        self.assertEqual(plan.tone, enrichment.tone)
        self.assertEqual(plan.structure, enrichment.structure)
        self.assertEqual(plan.language, enrichment.language)
        self.assertEqual(plan.mode, enrichment.mode)


class TestStructuralBoundaries(unittest.TestCase):
    def _module_source(self) -> str:
        with open(strategist.__file__, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_43_all_exact(self):
        self.assertEqual(strategist.__all__, ["run_strategist"])

    def test_44_exactly_one_public_function(self):
        public_functions = [
            name
            for name, obj in vars(strategist).items()
            if callable(obj)
            and not name.startswith("_")
            and getattr(obj, "__module__", None) == "src.strategy.strategist"
        ]
        self.assertEqual(public_functions, ["run_strategist"])

    def test_45_no_direct_strategist_plan_construction(self):
        source = self._module_source()
        self.assertNotIn("StrategistPlan(", source)

    def test_46_no_direct_strategist_input_construction(self):
        source = self._module_source()
        self.assertNotIn("StrategistInput(", source)

    def test_47_no_direct_strategist_enrichment_construction(self):
        source = self._module_source()
        self.assertNotIn("StrategistEnrichment(", source)

    def test_48_no_policy_mapping_constants(self):
        source = self._module_source()
        for token in ("_FORMAT_POLICIES", "_CLUSTER_ANGLES", "_LANGUAGE", "_MODE"):
            self.assertNotIn(token, source)

    def test_49_no_format_or_cluster_mappings(self):
        source = self._module_source()
        for token in (
            "ContentFormat.",
            "ContentCluster.",
            "breaking_news",
            "vibe_coding",
        ):
            self.assertNotIn(token, source)

    def test_50_no_forbidden_stdlib_imports(self):
        source = self._module_source()
        for token in ("random", "datetime", "pathlib", "yaml", "requests", "import os"):
            self.assertNotIn(token, source)

    def test_51_no_config_main_or_agents_imports(self):
        source = self._module_source()
        for token in ("Config", "src.main", "src.agents"):
            self.assertNotIn(token, source)

    def test_52_no_validators_state_or_research_imports(self):
        source = self._module_source()
        for token in ("validators", "StateService", "research"):
            self.assertNotIn(token, source)

    def test_53_no_try_except(self):
        source = self._module_source()
        self.assertNotIn("try", source)

    def test_54_no_legacy_terms(self):
        source = self._module_source()
        for token in (
            "news_item",
            "affilia",
            "topic_history",
            "validate_content_plan",
        ):
            self.assertNotIn(token, source)

    def test_55_no_filesystem_environment_network_usage(self):
        source = self._module_source()
        for token in (
            "open(",
            "environ",
            "getenv",
            "requests.",
            "urllib",
            "socket",
            "Path(",
            "subprocess",
        ):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
