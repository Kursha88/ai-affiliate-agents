"""Step 17F unit tests: research-phase lifecycle / orchestration policy.

Covers STRATEGY_READY routing, intrinsic-format gating (COMPARISON /
EXPERIMENT), the exact research/experiment status-to-lifecycle policies,
MANUAL_REVIEW precedence over pending, no-op identity on pending,
candidate and plan/requirements consistency validation with exact
messages, extra non-required result handling, the no-work invariant,
delegation to the Stage 16C transition, package/result immutability,
determinism, and structural AST guarantees (planner ownership, status
vocabularies, field access boundaries, no artifact coupling).
"""

import ast
import unittest
from pathlib import Path

from src.content.content_package_lifecycle import transition_package_stage
from src.domain.content_package import (
    ContentPackageV2,
    PackageStage,
    PublicationState,
    QualityState,
    SourceProvenance,
)
from src.domain.research_execution import (
    ExperimentExecutionResult,
    ExperimentExecutionStatus,
    ExperimentObservation,
    ExperimentPlan,
    EvidenceKind,
    EvidenceRecord,
    ResearchExecutionResult,
    ResearchExecutionStatus,
    ResearchRequirement,
    ResearchRequirementKind,
    RequirementOrigin,
)
from src.domain.strategy import ContentCluster, ContentFormat, TargetPlatform
from src.domain.strategist import StrategistPlan
from src.research.research_phase_orchestrator import (
    advance_research_phase,
    determine_research_phase_target,
    research_phase_required,
)
from src.research.research_requirement_planner import (
    plan_experiment,
    plan_research_requirements,
)

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "research"
    / "research_phase_orchestrator.py"
)

CREATED_AT = "2026-09-19T10:00:00+00:00"
UPDATED_AT = "2026-09-19T13:00:00+00:00"


def _plan(**overrides) -> StrategistPlan:
    defaults = dict(
        candidate_id="cand-123",
        topic="Example AI tool",
        content_cluster=ContentCluster.AI_TOOLS,
        content_format=ContentFormat.TOOL_DISCOVERY,
        target_platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
        research_required=False,
        experiment_required=False,
        angle="angle",
        hook="hook",
        objective="objective",
        cta="cta",
        cta_link="https://example.com/tool",
        tone="tone",
        structure=("context", "body", "cta"),
        language="ru",
        mode="growth",
    )
    defaults.update(overrides)
    return StrategistPlan(**defaults)


PROVENANCE = SourceProvenance(
    candidate_id="cand-123",
    source_url="https://example.com/tool",
    source_name="example",
    source_type="github",
    discovered_at="2026-09-19T09:00:00+00:00",
    published_at="2026-09-19T08:00:00+00:00",
    verification_status="verified",
    verification_confidence=0.91,
)


def _package(**overrides) -> ContentPackageV2:
    defaults = dict(
        package_id="pkg-123",
        candidate_id="cand-123",
        strategy=_plan(),
        provenance=PROVENANCE,
        stage=PackageStage.STRATEGY_READY,
        quality_state=QualityState.NOT_CHECKED,
        publication_state=PublicationState.NOT_READY,
        artifacts=(),
        platform_variants=(),
        analytics_links=(),
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        legacy_content_id=None,
    )
    defaults.update(overrides)
    return ContentPackageV2(**defaults)


def _research_result(package, *, status=ResearchExecutionStatus.COMPLETED, requirements=None,
                     candidate_id=None) -> ResearchExecutionResult:
    """Research result built from the package's ACTUAL planned requirements."""
    return ResearchExecutionResult(
        candidate_id=package.candidate_id if candidate_id is None else candidate_id,
        requirements=(
            plan_research_requirements(package.strategy)
            if requirements is None
            else requirements
        ),
        evidence=(
            EvidenceRecord(
                evidence_id="evidence-1",
                kind=EvidenceKind.COMPARISON_TARGET,
                title="Alternative Tool",
                source_url="https://example.com/alternative",
                source_name="Example",
                captured_at="2026-09-19T11:00:00+00:00",
                summary="A credible comparison target.",
                metadata={"source": "test"},
            ),
        ),
        status=status,
        started_at="2026-09-19T11:00:00+00:00",
        completed_at="2026-09-19T11:05:00+00:00",
        notes="",
    )


def _experiment_result(package, *, status=ExperimentExecutionStatus.COMPLETED,
                       plan=None, candidate_id=None) -> ExperimentExecutionResult:
    """Experiment result built from the package's ACTUAL planned plan."""
    return ExperimentExecutionResult(
        candidate_id=package.candidate_id if candidate_id is None else candidate_id,
        plan=plan_experiment(package.strategy) if plan is None else plan,
        observations=(
            ExperimentObservation(
                observation_id="obs-1",
                label="manual_steps",
                value="3",
                notes="Observed during offline test",
                metadata={"source": "test"},
            ),
        ),
        status=status,
        started_at="2026-09-19T12:00:00+00:00",
        completed_at="2026-09-19T12:05:00+00:00",
        conclusion="Observed practical result",
        notes="",
    )


class TestResearchPhaseRequired(unittest.TestCase):
    def test_no_work_when_prompt_without_flags(self):
        package = _package(
            strategy=_plan(
                content_format=ContentFormat.PROMPT,
                research_required=False,
                experiment_required=False,
            )
        )
        self.assertIs(research_phase_required(package), False)

    def test_true_for_intrinsic_comparison_research(self):
        package = _package(
            strategy=_plan(content_format=ContentFormat.COMPARISON)
        )
        self.assertIs(research_phase_required(package), True)

    def test_true_for_intrinsic_experiment_format(self):
        package = _package(
            strategy=_plan(content_format=ContentFormat.EXPERIMENT)
        )
        self.assertIs(research_phase_required(package), True)

    def test_true_for_explicit_research_flag(self):
        package = _package(
            strategy=_plan(
                content_format=ContentFormat.PROMPT, research_required=True
            )
        )
        self.assertIs(research_phase_required(package), True)

    def test_true_for_explicit_experiment_flag(self):
        package = _package(
            strategy=_plan(
                content_format=ContentFormat.PROMPT, experiment_required=True
            )
        )
        self.assertIs(research_phase_required(package), True)


class TestStrategyReadyRouting(unittest.TestCase):
    def test_intrinsic_comparison_routes_to_research_pending(self):
        package = _package(strategy=_plan(content_format=ContentFormat.COMPARISON))
        self.assertIs(
            determine_research_phase_target(package), PackageStage.RESEARCH_PENDING
        )
        result_package = advance_research_phase(package, updated_at=UPDATED_AT)
        self.assertIsNot(result_package, package)
        self.assertIs(result_package.stage, PackageStage.RESEARCH_PENDING)
        self.assertEqual(result_package.updated_at, UPDATED_AT)

    def test_intrinsic_experiment_format_routes_to_research_pending(self):
        package = _package(strategy=_plan(content_format=ContentFormat.EXPERIMENT))
        self.assertIs(
            determine_research_phase_target(package), PackageStage.RESEARCH_PENDING
        )

    def test_explicit_flags_route_to_research_pending(self):
        for overrides in (
            dict(content_format=ContentFormat.PROMPT, research_required=True),
            dict(content_format=ContentFormat.PROMPT, experiment_required=True),
        ):
            with self.subTest(**overrides):
                package = _package(strategy=_plan(**overrides))
                self.assertIs(
                    determine_research_phase_target(package),
                    PackageStage.RESEARCH_PENDING,
                )

    def test_no_gates_route_directly_to_creation_pending(self):
        package = _package(
            strategy=_plan(
                content_format=ContentFormat.PROMPT,
                research_required=False,
                experiment_required=False,
            )
        )
        self.assertIs(
            determine_research_phase_target(package), PackageStage.CREATION_PENDING
        )
        result_package = advance_research_phase(package, updated_at=UPDATED_AT)
        self.assertIs(result_package.stage, PackageStage.CREATION_PENDING)

    def test_strategy_ready_ignores_supplied_results(self):
        mismatched_research = _research_result(
            _package(strategy=_plan(content_format=ContentFormat.PROMPT)),
            status=ResearchExecutionStatus.FAILED,
            candidate_id="foreign-candidate",
        )
        mismatched_experiment = _experiment_result(
            _package(strategy=_plan(content_format=ContentFormat.PROMPT)),
            status=ExperimentExecutionStatus.INCONCLUSIVE,
            candidate_id="foreign-candidate",
        )
        comparison_package = _package(
            strategy=_plan(content_format=ContentFormat.COMPARISON)
        )
        self.assertIs(
            determine_research_phase_target(
                comparison_package,
                research_result=mismatched_research,
                experiment_result=mismatched_experiment,
            ),
            PackageStage.RESEARCH_PENDING,
        )
        prompt_package = _package(
            strategy=_plan(
                content_format=ContentFormat.PROMPT,
                research_required=False,
                experiment_required=False,
            )
        )
        self.assertIs(
            determine_research_phase_target(
                prompt_package,
                research_result=mismatched_research,
                experiment_result=mismatched_experiment,
            ),
            PackageStage.CREATION_PENDING,
        )


class TestWrongStage(unittest.TestCase):
    def test_unsupported_stages_raise_exact_error(self):
        unsupported = (
            PackageStage.RESEARCH_READY,
            PackageStage.CREATION_PENDING,
            PackageStage.CONTENT_READY,
            PackageStage.ADAPTATION_PENDING,
            PackageStage.VARIANTS_READY,
            PackageStage.QA_PENDING,
            PackageStage.APPROVED,
            PackageStage.PUBLISHING,
            PackageStage.PUBLISHED,
            PackageStage.ANALYZED,
            PackageStage.ARCHIVED,
            PackageStage.MANUAL_REVIEW,
        )
        for stage in unsupported:
            with self.subTest(stage=stage.value):
                package = _package(stage=stage)
                with self.assertRaises(ValueError) as ctx:
                    determine_research_phase_target(package)
                self.assertEqual(
                    str(ctx.exception),
                    "research phase orchestration requires strategy_ready or research_pending stage",
                )


class TestResearchPendingNoWork(unittest.TestCase):
    def test_inconsistent_research_pending_raises_exact_error(self):
        package = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(
                content_format=ContentFormat.PROMPT,
                research_required=False,
                experiment_required=False,
            ),
        )
        extra_research = _research_result(package, status=ResearchExecutionStatus.FAILED)
        extra_experiment = _experiment_result(
            package, status=ExperimentExecutionStatus.INCONCLUSIVE
        )
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(
                package,
                research_result=extra_research,
                experiment_result=extra_experiment,
            )
        self.assertEqual(
            str(ctx.exception),
            "research_pending package has no planned research or experiment work",
        )

    def test_no_work_check_precedes_candidate_validation(self):
        package = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(
                content_format=ContentFormat.PROMPT,
                research_required=False,
                experiment_required=False,
            ),
        )
        foreign = _research_result(package, candidate_id="foreign-candidate")
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(package, research_result=foreign)
        self.assertEqual(
            str(ctx.exception),
            "research_pending package has no planned research or experiment work",
        )


class TestResearchOnlyGate(unittest.TestCase):
    def setUp(self):
        self.package = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(content_format=ContentFormat.COMPARISON),
        )

    def test_completed_reaches_research_ready(self):
        result = _research_result(self.package, status=ResearchExecutionStatus.COMPLETED)
        self.assertIs(
            determine_research_phase_target(self.package, research_result=result),
            PackageStage.RESEARCH_READY,
        )
        advanced = advance_research_phase(
            self.package, research_result=result, updated_at=UPDATED_AT
        )
        self.assertIsNot(advanced, self.package)
        self.assertIs(advanced.stage, PackageStage.RESEARCH_READY)
        self.assertEqual(advanced.updated_at, UPDATED_AT)

    def test_missing_result_is_pending(self):
        self.assertIsNone(determine_research_phase_target(self.package))
        advanced = advance_research_phase(self.package, updated_at=UPDATED_AT)
        self.assertIs(advanced, self.package)
        self.assertEqual(advanced.updated_at, CREATED_AT)

    def test_not_started_is_pending(self):
        result = _research_result(self.package, status=ResearchExecutionStatus.NOT_STARTED)
        self.assertIsNone(
            determine_research_phase_target(self.package, research_result=result)
        )
        advanced = advance_research_phase(
            self.package, research_result=result, updated_at=UPDATED_AT
        )
        self.assertIs(advanced, self.package)

    def test_insufficient_failed_manual_review_reach_manual_review(self):
        for status in (
            ResearchExecutionStatus.INSUFFICIENT,
            ResearchExecutionStatus.FAILED,
            ResearchExecutionStatus.MANUAL_REVIEW,
        ):
            with self.subTest(status=status.value):
                result = _research_result(self.package, status=status)
                self.assertIs(
                    determine_research_phase_target(
                        self.package, research_result=result
                    ),
                    PackageStage.MANUAL_REVIEW,
                )

    def test_extra_experiment_result_ignored_for_lifecycle(self):
        result = _research_result(self.package, status=ResearchExecutionStatus.COMPLETED)
        extra = _experiment_result(
            self.package,
            status=ExperimentExecutionStatus.INCONCLUSIVE,
            plan=ExperimentPlan(
                experiment_id="cand-123:experiment",
                candidate_id="cand-123",
                hypothesis="arbitrary",
                procedure=("step",),
                success_criteria=("criterion",),
                required=False,
            ),
        )
        self.assertIs(
            determine_research_phase_target(
                self.package, research_result=result, experiment_result=extra
            ),
            PackageStage.RESEARCH_READY,
        )

    def test_extra_foreign_experiment_result_still_rejected(self):
        result = _research_result(self.package, status=ResearchExecutionStatus.COMPLETED)
        foreign = _experiment_result(
            self.package,
            status=ExperimentExecutionStatus.COMPLETED,
            candidate_id="foreign-candidate",
        )
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(
                self.package, research_result=result, experiment_result=foreign
            )
        self.assertEqual(
            str(ctx.exception),
            "candidate_id mismatch between package and experiment result",
        )


class TestExperimentOnlyGate(unittest.TestCase):
    def setUp(self):
        self.package = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(content_format=ContentFormat.EXPERIMENT),
        )
        self.assertEqual(plan_research_requirements(self.package.strategy), ())

    def test_completed_reaches_research_ready(self):
        result = _experiment_result(
            self.package, status=ExperimentExecutionStatus.COMPLETED
        )
        self.assertIs(
            determine_research_phase_target(self.package, experiment_result=result),
            PackageStage.RESEARCH_READY,
        )
        advanced = advance_research_phase(
            self.package, experiment_result=result, updated_at=UPDATED_AT
        )
        self.assertIs(advanced.stage, PackageStage.RESEARCH_READY)

    def test_missing_result_is_pending(self):
        self.assertIsNone(determine_research_phase_target(self.package))
        self.assertIs(advance_research_phase(self.package, updated_at=UPDATED_AT), self.package)

    def test_not_started_is_pending(self):
        result = _experiment_result(
            self.package, status=ExperimentExecutionStatus.NOT_STARTED
        )
        self.assertIsNone(
            determine_research_phase_target(self.package, experiment_result=result)
        )

    def test_inconclusive_failed_manual_review_reach_manual_review(self):
        for status in (
            ExperimentExecutionStatus.INCONCLUSIVE,
            ExperimentExecutionStatus.FAILED,
            ExperimentExecutionStatus.MANUAL_REVIEW,
        ):
            with self.subTest(status=status.value):
                result = _experiment_result(self.package, status=status)
                self.assertIs(
                    determine_research_phase_target(
                        self.package, experiment_result=result
                    ),
                    PackageStage.MANUAL_REVIEW,
                )

    def test_extra_research_result_ignored_for_lifecycle(self):
        result = _experiment_result(
            self.package, status=ExperimentExecutionStatus.COMPLETED
        )
        extra = _research_result(
            self.package,
            status=ResearchExecutionStatus.FAILED,
            requirements=(
                ResearchRequirement(
                    requirement_id="arbitrary",
                    kind=ResearchRequirementKind.PRIMARY_SOURCE,
                    origin=RequirementOrigin.MANUAL,
                    query="anything",
                    minimum_items=1,
                    required=True,
                ),
            ),
        )
        self.assertIs(
            determine_research_phase_target(
                self.package, research_result=extra, experiment_result=result
            ),
            PackageStage.RESEARCH_READY,
        )

    def test_extra_foreign_research_result_still_rejected(self):
        result = _experiment_result(
            self.package, status=ExperimentExecutionStatus.COMPLETED
        )
        foreign = _research_result(
            self.package,
            status=ResearchExecutionStatus.COMPLETED,
            candidate_id="foreign-candidate",
        )
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(
                self.package, research_result=foreign, experiment_result=result
            )
        self.assertEqual(
            str(ctx.exception),
            "candidate_id mismatch between package and research result",
        )


class TestBothGates(unittest.TestCase):
    def setUp(self):
        self.package = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(
                content_format=ContentFormat.COMPARISON, experiment_required=True
            ),
        )
        self.assertTrue(plan_research_requirements(self.package.strategy))
        self.assertIsNotNone(plan_experiment(self.package.strategy))

    def test_both_completed_reaches_research_ready(self):
        research = _research_result(self.package, status=ResearchExecutionStatus.COMPLETED)
        experiment = _experiment_result(
            self.package, status=ExperimentExecutionStatus.COMPLETED
        )
        self.assertIs(
            determine_research_phase_target(
                self.package, research_result=research, experiment_result=experiment
            ),
            PackageStage.RESEARCH_READY,
        )
        advanced = advance_research_phase(
            self.package,
            research_result=research,
            experiment_result=experiment,
            updated_at=UPDATED_AT,
        )
        self.assertIs(advanced.stage, PackageStage.RESEARCH_READY)

    def test_one_missing_is_pending(self):
        research = _research_result(self.package, status=ResearchExecutionStatus.COMPLETED)
        experiment = _experiment_result(
            self.package, status=ExperimentExecutionStatus.COMPLETED
        )
        self.assertIsNone(
            determine_research_phase_target(
                self.package, research_result=research
            )
        )
        self.assertIsNone(
            determine_research_phase_target(
                self.package, experiment_result=experiment
            )
        )

    def test_manual_review_precedes_pending(self):
        research = _research_result(self.package, status=ResearchExecutionStatus.COMPLETED)
        experiment = _experiment_result(
            self.package, status=ExperimentExecutionStatus.COMPLETED
        )
        insufficient = _research_result(
            self.package, status=ResearchExecutionStatus.INSUFFICIENT
        )
        failed = _research_result(self.package, status=ResearchExecutionStatus.FAILED)
        inconclusive = _experiment_result(
            self.package, status=ExperimentExecutionStatus.INCONCLUSIVE
        )
        not_started = _experiment_result(
            self.package, status=ExperimentExecutionStatus.NOT_STARTED
        )
        cases = (
            (insufficient, None, "research insufficient, experiment missing"),
            (None, inconclusive, "research missing, experiment inconclusive"),
            (failed, not_started, "research failed, experiment not started"),
        )
        for research_result, experiment_result, label in cases:
            with self.subTest(case=label):
                self.assertIs(
                    determine_research_phase_target(
                        self.package,
                        research_result=research_result,
                        experiment_result=experiment_result,
                    ),
                    PackageStage.MANUAL_REVIEW,
                )
        # Sanity: complete pair still reaches RESEARCH_READY.
        self.assertIs(
            determine_research_phase_target(
                self.package, research_result=research, experiment_result=experiment
            ),
            PackageStage.RESEARCH_READY,
        )


class TestConsistencyValidation(unittest.TestCase):
    def setUp(self):
        self.package = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(
                content_format=ContentFormat.COMPARISON, experiment_required=True
            ),
        )

    def test_research_candidate_mismatch_raises_exact_error(self):
        result = _research_result(self.package, candidate_id="other")
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(self.package, research_result=result)
        self.assertEqual(
            str(ctx.exception),
            "candidate_id mismatch between package and research result",
        )

    def test_experiment_candidate_mismatch_raises_exact_error(self):
        result = _experiment_result(self.package, candidate_id="other")
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(self.package, experiment_result=result)
        self.assertEqual(
            str(ctx.exception),
            "candidate_id mismatch between package and experiment result",
        )

    def test_research_mismatch_reported_before_experiment_mismatch(self):
        research = _research_result(self.package, candidate_id="other")
        experiment = _experiment_result(self.package, candidate_id="other-too")
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(
                self.package, research_result=research, experiment_result=experiment
            )
        self.assertEqual(
            str(ctx.exception),
            "candidate_id mismatch between package and research result",
        )

    def test_empty_requirements_mismatch_raises_exact_error(self):
        result = _research_result(self.package, requirements=())
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(self.package, research_result=result)
        self.assertEqual(
            str(ctx.exception),
            "research result requirements do not match planned requirements",
        )

    def test_nonempty_different_requirements_mismatch_raises(self):
        different = (
            ResearchRequirement(
                requirement_id="cand-123:format:primary_source",
                kind=ResearchRequirementKind.PRIMARY_SOURCE,
                origin=RequirementOrigin.CONTENT_FORMAT,
                query="different query",
                minimum_items=2,
                required=False,
            ),
        )
        result = _research_result(self.package, requirements=different)
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(self.package, research_result=result)
        self.assertEqual(
            str(ctx.exception),
            "research result requirements do not match planned requirements",
        )

    def test_experiment_plan_mismatch_raises_exact_error(self):
        different_plan = ExperimentPlan(
            experiment_id="cand-123:experiment",
            candidate_id="cand-123",
            hypothesis="A different hypothesis",
            procedure=("step",),
            success_criteria=("criterion",),
            required=True,
        )
        result = _experiment_result(self.package, plan=different_plan)
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(self.package, experiment_result=result)
        self.assertEqual(
            str(ctx.exception),
            "experiment result plan does not match planned experiment",
        )

    def test_same_experiment_id_alone_is_not_accepted(self):
        planned = plan_experiment(self.package.strategy)
        forged = ExperimentPlan(
            experiment_id=planned.experiment_id,
            candidate_id=planned.candidate_id,
            hypothesis="Forged hypothesis text",
            procedure=planned.procedure,
            success_criteria=planned.success_criteria,
            required=planned.required,
        )
        result = _experiment_result(self.package, plan=forged)
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(self.package, experiment_result=result)
        self.assertEqual(
            str(ctx.exception),
            "experiment result plan does not match planned experiment",
        )

    def test_consistency_validation_precedes_status_policy(self):
        mismatched = _research_result(
            self.package, status=ResearchExecutionStatus.INSUFFICIENT, requirements=()
        )
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(self.package, research_result=mismatched)
        self.assertEqual(
            str(ctx.exception),
            "research result requirements do not match planned requirements",
        )
        forged_plan = ExperimentPlan(
            experiment_id="cand-123:experiment",
            candidate_id="cand-123",
            hypothesis="different",
            procedure=("x",),
            success_criteria=("y",),
            required=True,
        )
        bad_experiment = _experiment_result(
            self.package,
            status=ExperimentExecutionStatus.INCONCLUSIVE,
            plan=forged_plan,
        )
        with self.assertRaises(ValueError) as ctx:
            determine_research_phase_target(
                self.package, experiment_result=bad_experiment
            )
        self.assertEqual(
            str(ctx.exception),
            "experiment result plan does not match planned experiment",
        )


class TestNoopAndUpdateBehavior(unittest.TestCase):
    def setUp(self):
        self.package = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(content_format=ContentFormat.COMPARISON),
            updated_at="old",
        )

    def test_noop_preserves_identity_and_updated_at(self):
        result = advance_research_phase(self.package, updated_at="new")
        self.assertIs(result, self.package)
        self.assertEqual(result.updated_at, "old")

    def test_transition_preserves_raw_updated_at(self):
        result = _research_result(
            self.package, status=ResearchExecutionStatus.COMPLETED
        )
        advanced = advance_research_phase(
            self.package, research_result=result, updated_at="not-a-timestamp"
        )
        self.assertEqual(advanced.updated_at, "not-a-timestamp")


class TestImmutabilityAndDeterminism(unittest.TestCase):
    def test_transition_preserves_package_identity_fields(self):
        package = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(content_format=ContentFormat.COMPARISON),
        )
        result = _research_result(package, status=ResearchExecutionStatus.COMPLETED)
        advanced = advance_research_phase(
            package, research_result=result, updated_at=UPDATED_AT
        )
        self.assertIsNot(advanced, package)
        self.assertIs(advanced.strategy, package.strategy)
        self.assertIs(advanced.provenance, package.provenance)
        self.assertIs(advanced.artifacts, package.artifacts)
        self.assertIs(advanced.platform_variants, package.platform_variants)
        self.assertIs(advanced.analytics_links, package.analytics_links)
        self.assertIs(advanced.quality_state, package.quality_state)
        self.assertIs(advanced.publication_state, package.publication_state)
        self.assertEqual(advanced.created_at, package.created_at)
        self.assertEqual(advanced.candidate_id, package.candidate_id)
        self.assertEqual(advanced.package_id, package.package_id)
        self.assertIs(advanced.stage, PackageStage.RESEARCH_READY)

    def test_results_unchanged_after_diagnosis_and_advance(self):
        package = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(
                content_format=ContentFormat.COMPARISON, experiment_required=True
            ),
        )
        research = _research_result(package, status=ResearchExecutionStatus.COMPLETED)
        experiment = _experiment_result(
            package, status=ExperimentExecutionStatus.COMPLETED
        )
        requirements = research.requirements
        plan = experiment.plan
        observations = experiment.observations
        determine_research_phase_target(
            package, research_result=research, experiment_result=experiment
        )
        advance_research_phase(
            package,
            research_result=research,
            experiment_result=experiment,
            updated_at=UPDATED_AT,
        )
        self.assertIs(research.requirements, requirements)
        self.assertIs(experiment.plan, plan)
        self.assertIs(experiment.observations, observations)

    def test_no_artifact_dependency(self):
        empty = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(content_format=ContentFormat.COMPARISON),
        )
        decorated = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=empty.strategy,
            artifacts=(
                __import__(
                    "src.domain.content_package", fromlist=["PackageArtifact"]
                ).PackageArtifact(
                    artifact_id="some-other:artifact",
                    kind=__import__(
                        "src.domain.content_package", fromlist=["ArtifactKind"]
                    ).ArtifactKind.SOURCE,
                    uri="memory://whatever",
                    title="Unrelated",
                    metadata={},
                ),
            ),
        )
        result = _research_result(empty, status=ResearchExecutionStatus.COMPLETED)
        self.assertIs(
            determine_research_phase_target(empty, research_result=result),
            PackageStage.RESEARCH_READY,
        )
        self.assertIs(
            determine_research_phase_target(decorated, research_result=result),
            PackageStage.RESEARCH_READY,
        )

    def test_determinism(self):
        package = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=_plan(content_format=ContentFormat.COMPARISON),
        )
        result = _research_result(package, status=ResearchExecutionStatus.COMPLETED)
        kwargs = dict(research_result=result)
        self.assertIs(
            determine_research_phase_target(package, **kwargs),
            determine_research_phase_target(package, **kwargs),
        )
        other = _package(
            stage=PackageStage.RESEARCH_PENDING,
            strategy=package.strategy,
        )
        first = advance_research_phase(
            other, research_result=result, updated_at=UPDATED_AT
        )
        second = advance_research_phase(
            other, research_result=result, updated_at=UPDATED_AT
        )
        self.assertEqual(first, second)
        self.assertIsNot(first, second)


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees for the orchestrator module
# ──────────────────────────────────────────────────────────────────────

def _module_tree() -> ast.Module:
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def _module_ids(tree: ast.Module) -> set:
    """All Name ids, Attribute attrs, and import names (docstring-immune)."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            ids.add(node.id)
        elif isinstance(node, ast.Attribute):
            ids.add(node.attr)
        elif isinstance(node, ast.Import):
            ids.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                ids.add(node.module)
            ids.update(alias.name for alias in node.names)
    return ids


class TestOrchestratorStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _module_tree()
        cls.ids = _module_ids(cls.tree)
        cls.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_exactly_three_module_level_functions(self):
        functions = [
            node for node in self.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(
            [f.name for f in functions],
            [
                "research_phase_required",
                "determine_research_phase_target",
                "advance_research_phase",
            ],
        )

    def test_all_is_exactly_three_functions(self):
        assigns = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        ]
        self.assertEqual(len(assigns), 1)
        values = [elt.value for elt in assigns[0].value.elts]
        self.assertEqual(
            values,
            [
                "research_phase_required",
                "determine_research_phase_target",
                "advance_research_phase",
            ],
        )

    def test_planner_calls_exist(self):
        for name in ("plan_research_requirements", "plan_experiment"):
            calls = [
                node for node in ast.walk(self.tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == name
            ]
            self.assertGreaterEqual(len(calls), 1)

    def test_exactly_one_transition_call_site(self):
        calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "transition_package_stage"
        ]
        self.assertEqual(len(calls), 1)

    def test_no_artifact_or_attachment_coupling(self):
        forbidden = {
            "ArtifactKind", "PackageArtifact", "attach_package_artifact",
            "attach_research_result", "attach_experiment_result",
        }
        leaks = sorted(token for token in forbidden if token in self.ids)
        self.assertEqual(leaks, [])

    def test_no_direct_flag_or_format_or_cluster_access(self):
        accessed = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "strategy"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "package"
        }
        self.assertEqual(accessed, set())

    def test_no_artifacts_or_metadata_access(self):
        accessed = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "package"
        }
        self.assertNotIn("artifacts", accessed)
        self.assertNotIn("quality_state", accessed)
        self.assertNotIn("publication_state", accessed)
        metadata_access = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute) and node.attr == "metadata"
        ]
        self.assertEqual(metadata_access, [])

    def test_result_evidence_observations_not_accessed(self):
        for local_name in ("research_result", "experiment_result"):
            accessed = {
                node.attr
                for node in ast.walk(self.tree)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == local_name
            }
            if local_name == "research_result":
                self.assertNotIn("evidence", accessed)
            else:
                self.assertNotIn("observations", accessed)

    def test_research_status_vocabulary_boundary(self):
        referenced = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ResearchExecutionStatus"
        }
        self.assertEqual(
            referenced,
            {"NOT_STARTED", "COMPLETED", "INSUFFICIENT", "FAILED", "MANUAL_REVIEW"},
        )

    def test_experiment_status_vocabulary_boundary(self):
        referenced = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ExperimentExecutionStatus"
        }
        self.assertEqual(
            referenced,
            {"NOT_STARTED", "COMPLETED", "INCONCLUSIVE", "FAILED", "MANUAL_REVIEW"},
        )

    def test_exactly_six_value_error_sites_with_exact_messages(self):
        raises = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "ValueError"
        ]
        self.assertEqual(len(raises), 6)
        messages = sorted(
            node.exc.args[0].value for node in raises
            if isinstance(node.exc.args[0], ast.Constant)
        )
        self.assertEqual(
            messages,
            sorted(
                [
                    "research phase orchestration requires strategy_ready or research_pending stage",
                    "research_pending package has no planned research or experiment work",
                    "candidate_id mismatch between package and research result",
                    "candidate_id mismatch between package and experiment result",
                    "research result requirements do not match planned requirements",
                    "experiment result plan does not match planned experiment",
                ]
            ),
        )

    def test_no_try_sorting_or_collection_mutation(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, (ast.Try, ast.AugAssign))
        self.assertNotIn("sorted", self.ids)
        # Input collections are never mutated: no attribute assignment on
        # package/result objects anywhere in the module.
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                self.fail("production module must not assign attributes")

    def test_no_forbidden_imports_or_references(self):
        forbidden = {
            # Generation sources.
            "datetime", "time", "uuid", "hashlib", "random",
            # Persistence / config / DB.
            "StateService", "sqlite3", "Config", "repository", "database",
            # Filesystem / network / process.
            "os", "pathlib", "subprocess", "requests", "httpx", "urllib",
            "socket",
            # Serialization.
            "json", "pickle", "asdict", "to_dict", "from_dict", "serialize",
            "deserialize",
            # Format policy ownership must stay with 17B.
            "ContentFormat", "ResearchRequirementKind", "RequirementOrigin",
            # Rebuild helpers.
            "replace", "deepcopy",
        }
        leaks = sorted(token for token in forbidden if token in self.ids)
        self.assertEqual(leaks, [])

    def test_no_open_print_exec_eval_calls(self):
        call_names = {
            node.func.id
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertEqual(call_names & {"open", "print", "exec", "eval"}, set())

    def test_no_new_domain_types(self):
        class_defs = [
            node for node in self.tree.body if isinstance(node, ast.ClassDef)
        ]
        self.assertEqual(class_defs, [])


if __name__ == "__main__":
    unittest.main()
