"""Step 17A unit tests: research/experiment execution domain contracts.

Binds src.domain.research_execution to its intended shape: exact enum
vocabularies, frozen dataclasses with exact field order and no defaults,
identity preservation of nested plans and tuples, raw caller values
accepted without hidden validation, and the absence of methods, execution
logic, package coupling, strategy coupling, or side-effect coupling.
"""

import ast
import dataclasses
import unittest
from pathlib import Path

from src.domain.research_execution import (
    EvidenceKind,
    EvidenceRecord,
    ExperimentExecutionResult,
    ExperimentExecutionStatus,
    ExperimentObservation,
    ExperimentPlan,
    ResearchExecutionResult,
    ResearchExecutionStatus,
    ResearchRequirement,
    ResearchRequirementKind,
    RequirementOrigin,
)

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "domain" / "research_execution.py"
)

REQUIREMENT = ResearchRequirement(
    requirement_id="req-comparison-1",
    kind=ResearchRequirementKind.COMPARISON_TARGET,
    origin=RequirementOrigin.CONTENT_FORMAT,
    query="Find one credible alternative to the selected tool",
    minimum_items=1,
    required=True,
)

EVIDENCE = EvidenceRecord(
    evidence_id="evidence-1",
    kind=EvidenceKind.COMPARISON_TARGET,
    title="Alternative Tool",
    source_url="https://example.com/alternative",
    source_name="Example",
    captured_at="2026-09-19T15:00:00+00:00",
    summary="A credible comparison target.",
    metadata={"license": "free"},
)

PLAN = ExperimentPlan(
    experiment_id="exp-1",
    candidate_id="cand-123",
    hypothesis="The workflow reduces manual steps",
    procedure=(
        "Define the baseline workflow",
        "Run the candidate workflow",
        "Compare observable results",
    ),
    success_criteria=(
        "Fewer manual steps",
        "Same required output",
    ),
    required=True,
)

OBSERVATION = ExperimentObservation(
    observation_id="obs-1",
    label="manual_steps",
    value="3",
    notes="measured over one run",
    metadata={"runs": "1"},
)


class TestEnumContracts(unittest.TestCase):
    def test_requirement_origin_exact_values_and_order(self):
        self.assertEqual(
            [origin.value for origin in RequirementOrigin],
            ["select_flag", "content_format", "manual"],
        )

    def test_research_requirement_kind_exact_values_and_order(self):
        self.assertEqual(
            [kind.value for kind in ResearchRequirementKind],
            [
                "primary_source",
                "supporting_evidence",
                "comparison_target",
                "counterpoint",
                "implementation_details",
                "real_world_example",
            ],
        )

    def test_evidence_kind_exact_values_and_order(self):
        self.assertEqual(
            [kind.value for kind in EvidenceKind],
            [
                "primary_source",
                "supporting_source",
                "comparison_target",
                "counterpoint",
                "documentation",
                "repository",
                "real_world_example",
            ],
        )

    def test_research_execution_status_exact_values_and_order(self):
        self.assertEqual(
            [status.value for status in ResearchExecutionStatus],
            ["not_started", "completed", "insufficient", "failed", "manual_review"],
        )

    def test_experiment_execution_status_exact_values_and_order(self):
        self.assertEqual(
            [status.value for status in ExperimentExecutionStatus],
            ["not_started", "completed", "inconclusive", "failed", "manual_review"],
        )


class TestFrozenDataclasses(unittest.TestCase):
    def test_all_six_are_dataclasses_and_frozen(self):
        for cls in (
            ResearchRequirement,
            EvidenceRecord,
            ResearchExecutionResult,
            ExperimentPlan,
            ExperimentObservation,
            ExperimentExecutionResult,
        ):
            with self.subTest(cls=cls.__name__):
                self.assertTrue(dataclasses.is_dataclass(cls))
                self.assertIs(cls.__dataclass_params__.frozen, True)


class TestExactFieldOrder(unittest.TestCase):
    def test_research_requirement_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(ResearchRequirement)],
            ["requirement_id", "kind", "origin", "query", "minimum_items", "required"],
        )

    def test_evidence_record_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(EvidenceRecord)],
            [
                "evidence_id",
                "kind",
                "title",
                "source_url",
                "source_name",
                "captured_at",
                "summary",
                "metadata",
            ],
        )

    def test_research_execution_result_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(ResearchExecutionResult)],
            [
                "candidate_id",
                "requirements",
                "evidence",
                "status",
                "started_at",
                "completed_at",
                "notes",
            ],
        )

    def test_experiment_plan_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(ExperimentPlan)],
            [
                "experiment_id",
                "candidate_id",
                "hypothesis",
                "procedure",
                "success_criteria",
                "required",
            ],
        )

    def test_experiment_observation_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(ExperimentObservation)],
            ["observation_id", "label", "value", "notes", "metadata"],
        )

    def test_experiment_execution_result_field_order(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(ExperimentExecutionResult)],
            [
                "candidate_id",
                "plan",
                "observations",
                "status",
                "started_at",
                "completed_at",
                "conclusion",
                "notes",
            ],
        )


class TestNoDefaults(unittest.TestCase):
    def test_every_field_has_no_default_and_no_default_factory(self):
        for cls in (
            ResearchRequirement,
            EvidenceRecord,
            ResearchExecutionResult,
            ExperimentPlan,
            ExperimentObservation,
            ExperimentExecutionResult,
        ):
            for field in dataclasses.fields(cls):
                with self.subTest(cls=cls.__name__, field=field.name):
                    self.assertIs(field.default, dataclasses.MISSING)
                    self.assertIs(field.default_factory, dataclasses.MISSING)


class TestIdentityPreservation(unittest.TestCase):
    def test_research_result_preserves_tuples_by_identity(self):
        requirement_1 = REQUIREMENT
        requirement_2 = ResearchRequirement(
            requirement_id="req-primary-1",
            kind=ResearchRequirementKind.PRIMARY_SOURCE,
            origin=RequirementOrigin.SELECT_FLAG,
            query="Locate the official repository of the selected tool",
            minimum_items=1,
            required=True,
        )
        evidence_1 = EVIDENCE
        evidence_2 = EvidenceRecord(
            evidence_id="evidence-2",
            kind=EvidenceKind.REPOSITORY,
            title="Selected Tool Repository",
            source_url="https://example.com/tool",
            source_name="Example",
            captured_at="2026-09-19T15:05:00+00:00",
            summary="Primary repository of the selected tool.",
            metadata={"license": "mit"},
        )
        requirements = (requirement_1, requirement_2)
        evidence = (evidence_1, evidence_2)
        result = ResearchExecutionResult(
            candidate_id="cand-123",
            requirements=requirements,
            evidence=evidence,
            status=ResearchExecutionStatus.COMPLETED,
            started_at="2026-09-19T15:00:00+00:00",
            completed_at="2026-09-19T15:30:00+00:00",
            notes="ok",
        )
        self.assertIs(result.requirements, requirements)
        self.assertIs(result.evidence, evidence)

    def test_experiment_result_preserves_plan_and_observations_by_identity(self):
        plan = PLAN
        observation_1 = OBSERVATION
        observation_2 = ExperimentObservation(
            observation_id="obs-2",
            label="output_quality",
            value="same",
            notes="compared with baseline",
            metadata={},
        )
        observations = (observation_1, observation_2)
        result = ExperimentExecutionResult(
            candidate_id="cand-123",
            plan=plan,
            observations=observations,
            status=ExperimentExecutionStatus.COMPLETED,
            started_at="2026-09-19T16:00:00+00:00",
            completed_at="2026-09-19T16:20:00+00:00",
            conclusion="Fewer manual steps with same output",
            notes="ok",
        )
        self.assertIs(result.plan, plan)
        self.assertIs(result.observations, observations)


class TestValuePreservation(unittest.TestCase):
    def test_representative_requirement_values_survive_unchanged(self):
        self.assertEqual(REQUIREMENT.requirement_id, "req-comparison-1")
        self.assertIs(REQUIREMENT.kind, ResearchRequirementKind.COMPARISON_TARGET)
        self.assertIs(REQUIREMENT.origin, RequirementOrigin.CONTENT_FORMAT)
        self.assertEqual(
            REQUIREMENT.query, "Find one credible alternative to the selected tool"
        )
        self.assertEqual(REQUIREMENT.minimum_items, 1)
        self.assertIs(REQUIREMENT.required, True)

    def test_evidence_metadata_is_exact_mapping_object(self):
        metadata = {"license": "free"}
        record = EvidenceRecord(
            evidence_id="evidence-9",
            kind=EvidenceKind.DOCUMENTATION,
            title="Docs",
            source_url="https://example.com/docs",
            source_name="Example",
            captured_at="2026-09-19T15:00:00+00:00",
            summary="Documentation snapshot.",
            metadata=metadata,
        )
        self.assertIs(record.metadata, metadata)

    def test_representative_evidence_values_survive_unchanged(self):
        self.assertEqual(EVIDENCE.evidence_id, "evidence-1")
        self.assertIs(EVIDENCE.kind, EvidenceKind.COMPARISON_TARGET)
        self.assertEqual(EVIDENCE.title, "Alternative Tool")
        self.assertEqual(EVIDENCE.source_url, "https://example.com/alternative")
        self.assertEqual(EVIDENCE.source_name, "Example")
        self.assertEqual(EVIDENCE.captured_at, "2026-09-19T15:00:00+00:00")
        self.assertEqual(EVIDENCE.summary, "A credible comparison target.")

    def test_representative_experiment_values_survive_unchanged(self):
        self.assertEqual(PLAN.experiment_id, "exp-1")
        self.assertEqual(PLAN.candidate_id, "cand-123")
        self.assertEqual(PLAN.hypothesis, "The workflow reduces manual steps")
        self.assertEqual(
            PLAN.procedure,
            (
                "Define the baseline workflow",
                "Run the candidate workflow",
                "Compare observable results",
            ),
        )
        self.assertEqual(
            PLAN.success_criteria,
            ("Fewer manual steps", "Same required output"),
        )
        self.assertIs(PLAN.required, True)
        self.assertEqual(OBSERVATION.observation_id, "obs-1")
        self.assertEqual(OBSERVATION.label, "manual_steps")
        self.assertEqual(OBSERVATION.value, "3")

    def test_no_execution_occurs_when_constructing_experiment_contracts(self):
        result = ExperimentExecutionResult(
            candidate_id="cand-123",
            plan=PLAN,
            observations=(OBSERVATION,),
            status=ExperimentExecutionStatus.NOT_STARTED,
            started_at="2026-09-19T16:00:00+00:00",
            completed_at=None,
            conclusion="",
            notes="",
        )
        self.assertIs(result.status, ExperimentExecutionStatus.NOT_STARTED)
        self.assertIsNone(result.completed_at)
        self.assertIs(result.plan, PLAN)


class TestImmutability(unittest.TestCase):
    def test_research_requirement_assignment_raises(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            REQUIREMENT.minimum_items = 5

    def test_evidence_record_assignment_raises(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            EVIDENCE.title = "other"

    def test_research_execution_result_assignment_raises(self):
        result = ResearchExecutionResult(
            candidate_id="cand-123",
            requirements=(REQUIREMENT,),
            evidence=(EVIDENCE,),
            status=ResearchExecutionStatus.NOT_STARTED,
            started_at="2026-09-19T15:00:00+00:00",
            completed_at=None,
            notes="",
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.status = ResearchExecutionStatus.FAILED

    def test_experiment_plan_assignment_raises(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            PLAN.hypothesis = "other"

    def test_experiment_observation_assignment_raises(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            OBSERVATION.value = "other"

    def test_experiment_execution_result_assignment_raises(self):
        result = ExperimentExecutionResult(
            candidate_id="cand-123",
            plan=PLAN,
            observations=(OBSERVATION,),
            status=ExperimentExecutionStatus.NOT_STARTED,
            started_at="2026-09-19T16:00:00+00:00",
            completed_at=None,
            conclusion="",
            notes="",
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.conclusion = "other"


class TestContractHasNoMethods(unittest.TestCase):
    def test_no_owned_methods_on_contracts(self):
        for cls in (
            ResearchRequirement,
            EvidenceRecord,
            ResearchExecutionResult,
            ExperimentPlan,
            ExperimentObservation,
            ExperimentExecutionResult,
        ):
            for name in (
                "to_dict", "from_dict", "validate", "execute", "run",
                "transition", "attach",
            ):
                with self.subTest(cls=cls.__name__, name=name):
                    self.assertNotIn(name, cls.__dict__)


class TestAllowRawCallerValues(unittest.TestCase):
    def test_requirement_accepts_raw_values_without_validation(self):
        requirement = ResearchRequirement(
            requirement_id="req-raw",
            kind=ResearchRequirementKind.SUPPORTING_EVIDENCE,
            origin=RequirementOrigin.MANUAL,
            query="",
            minimum_items=-1,
            required=False,
        )
        self.assertEqual(requirement.query, "")
        self.assertEqual(requirement.minimum_items, -1)
        self.assertIs(requirement.required, False)

    def test_evidence_record_accepts_raw_values_without_validation(self):
        record = EvidenceRecord(
            evidence_id="evidence-raw",
            kind=EvidenceKind.SUPPORTING_SOURCE,
            title="",
            source_url="",
            source_name="",
            captured_at="not-a-timestamp",
            summary="",
            metadata={},
        )
        self.assertEqual(record.source_url, "")
        self.assertEqual(record.captured_at, "not-a-timestamp")

    def test_results_accept_completed_at_none(self):
        research = ResearchExecutionResult(
            candidate_id="cand-123",
            requirements=(REQUIREMENT,),
            evidence=(),
            status=ResearchExecutionStatus.NOT_STARTED,
            started_at="",
            completed_at=None,
            notes="",
        )
        experiment = ExperimentExecutionResult(
            candidate_id="cand-123",
            plan=PLAN,
            observations=(),
            status=ExperimentExecutionStatus.NOT_STARTED,
            started_at="",
            completed_at=None,
            conclusion="",
            notes="",
        )
        self.assertIsNone(research.completed_at)
        self.assertIsNone(experiment.completed_at)


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees for the contracts module
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


class TestNoCrossLayerCoupling(unittest.TestCase):
    def _assert_absent(self, tokens):
        tree = _module_tree()
        ids = _module_ids(tree)
        leaks = sorted(token for token in tokens if token in ids)
        self.assertEqual(leaks, [])

    def test_no_package_or_strategy_coupling(self):
        self._assert_absent(
            [
                "ContentPackageV2",
                "PackageArtifact",
                "PackageStage",
                "attach_package_artifact",
                "transition_package_stage",
                "ContentCandidate",
                "StrategistPlan",
                "ContentFormat",
                "ContentCluster",
                "TargetPlatform",
                "StateService",
                "Config",
                "sqlite3",
            ]
        )

    def test_no_package_artifact_conversion_symbols(self):
        self._assert_absent(
            ["to_package_artifact", "build_package_artifact", "attach_package_artifact"]
        )

    def test_no_side_effect_or_execution_coupling(self):
        self._assert_absent(
            [
                "datetime", "time", "uuid", "hashlib", "random",
                "os", "pathlib", "subprocess", "requests", "httpx", "urllib",
                "socket",
                "publisher", "copywriter", "editor", "designer",
                "telegram", "x_client", "vk_client", "pinterest_client",
                "run_research", "execute_research", "search_web", "fetch_evidence",
                "run_experiment", "execute_experiment", "run_command", "run_process",
                "collect_observation", "build_requirements", "plan_research",
            ]
        )

    def test_no_open_print_exec_eval_calls(self):
        tree = _module_tree()
        call_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertEqual(call_names & {"open", "print", "exec", "eval"}, set())


class TestZeroFunctions(unittest.TestCase):
    def test_zero_module_level_function_definitions(self):
        tree = _module_tree()
        functions = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(functions, [])

    def test_module_contains_only_imports_enums_dataclasses_and_all(self):
        tree = _module_tree()
        for node in tree.body:
            with self.subTest(node=type(node).__name__):
                self.assertIsInstance(
                    node,
                    (
                        ast.Import,
                        ast.ImportFrom,
                        ast.ClassDef,
                        ast.Assign,
                        ast.AnnAssign,
                        ast.Expr,
                    ),
                )


class TestModuleAll(unittest.TestCase):
    def test_all_is_exactly_the_eleven_contract_names(self):
        tree = _module_tree()
        assigns = [
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        ]
        self.assertEqual(len(assigns), 1)
        values = [elt.value for elt in assigns[0].value.elts]
        self.assertEqual(
            values,
            [
                "RequirementOrigin",
                "ResearchRequirementKind",
                "EvidenceKind",
                "ResearchExecutionStatus",
                "ExperimentExecutionStatus",
                "ResearchRequirement",
                "EvidenceRecord",
                "ResearchExecutionResult",
                "ExperimentPlan",
                "ExperimentObservation",
                "ExperimentExecutionResult",
            ],
        )


if __name__ == "__main__":
    unittest.main()
