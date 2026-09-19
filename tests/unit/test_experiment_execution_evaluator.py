"""Step 17D unit tests: deterministic offline experiment execution evaluator.

Covers observation-presence-only status policy (COMPLETED vs INCONCLUSIVE),
proof that plan semantics (required flag, hypothesis, procedure, success
criteria) and observation content never affect status, identity
preservation of plan/observations/metadata, exact caller value
preservation (conclusion, notes, timestamps), determinism, the status
vocabulary boundary (only COMPLETED/INCONCLUSIVE), and structural AST
guarantees including the strict field-access boundary
(plan.candidate_id + tuple truthiness only).
"""

import ast
import unittest
from pathlib import Path

from src.domain.research_execution import (
    ExperimentExecutionResult,
    ExperimentExecutionStatus,
    ExperimentObservation,
    ExperimentPlan,
)
from src.research.experiment_execution_evaluator import evaluate_experiment_execution

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "research"
    / "experiment_execution_evaluator.py"
)


def _plan(**overrides) -> ExperimentPlan:
    defaults = dict(
        experiment_id="cand-123:experiment",
        candidate_id="cand-123",
        hypothesis="Testing Example AI tool produces an observable practical result",
        procedure=(
            "Define the expected result and baseline",
            "Run the described approach in a controlled test",
            "Record the observable outcome",
            "Compare the outcome with the expected result",
        ),
        success_criteria=(
            "The procedure can be completed as described",
            "The outcome is observable and can support a practical conclusion",
        ),
        required=True,
    )
    defaults.update(overrides)
    return ExperimentPlan(**defaults)


def _observation(observation_id="obs-1", **overrides) -> ExperimentObservation:
    defaults = dict(
        label="manual_steps",
        value="3",
        notes="Observed during offline test",
        metadata={"source": "test"},
    )
    defaults.update(overrides)
    return ExperimentObservation(observation_id=observation_id, **defaults)


def _evaluate(plan=None, observations=None, **overrides):
    params = dict(
        plan=_plan() if plan is None else plan,
        observations=observations if observations is not None else (),
        started_at="2026-09-19T17:00:00+00:00",
        completed_at="2026-09-19T17:30:00+00:00",
        conclusion="",
        notes="",
    )
    params.update(overrides)
    return evaluate_experiment_execution(**params)


class TestCompleted(unittest.TestCase):
    def test_one_observation_completes_with_exact_values(self):
        plan = _plan()
        observations = (_observation(),)
        result = _evaluate(
            plan=plan,
            observations=observations,
            started_at="2026-09-19T17:00:00+00:00",
            completed_at="2026-09-19T17:30:00+00:00",
            conclusion="The workflow reduced observable manual steps.",
            notes="Manual offline observation.",
        )
        self.assertIsInstance(result, ExperimentExecutionResult)
        self.assertIs(result.status, ExperimentExecutionStatus.COMPLETED)
        self.assertEqual(result.candidate_id, "cand-123")
        self.assertIs(result.plan, plan)
        self.assertIs(result.observations, observations)
        self.assertEqual(result.started_at, "2026-09-19T17:00:00+00:00")
        self.assertEqual(result.completed_at, "2026-09-19T17:30:00+00:00")
        self.assertEqual(
            result.conclusion, "The workflow reduced observable manual steps."
        )
        self.assertEqual(result.notes, "Manual offline observation.")


class TestInconclusive(unittest.TestCase):
    def test_empty_observations_are_inconclusive(self):
        plan = _plan()
        observations = ()
        result = _evaluate(plan=plan, observations=observations)
        self.assertIs(result.status, ExperimentExecutionStatus.INCONCLUSIVE)
        self.assertIs(result.observations, observations)
        self.assertEqual(result.conclusion, "")
        self.assertEqual(result.notes, "")


class TestObservationPresenceOnly(unittest.TestCase):
    def test_one_observation_is_enough(self):
        result = _evaluate(observations=(_observation(),))
        self.assertIs(result.status, ExperimentExecutionStatus.COMPLETED)

    def test_three_observations_completed_with_exact_order(self):
        first = _observation("obs-1")
        second = _observation("obs-2")
        third = _observation("obs-3")
        observations = (first, second, third)
        result = _evaluate(observations=observations)
        self.assertIs(result.status, ExperimentExecutionStatus.COMPLETED)
        self.assertIs(result.observations, observations)
        self.assertIs(result.observations[0], first)
        self.assertIs(result.observations[1], second)
        self.assertIs(result.observations[2], third)

    def test_duplicate_observation_ids_preserved_without_error(self):
        observations = (_observation("same-id", label="a"), _observation("same-id", label="b"))
        result = _evaluate(observations=observations)
        self.assertIs(result.status, ExperimentExecutionStatus.COMPLETED)
        self.assertIs(result.observations, observations)
        self.assertEqual(len(result.observations), 2)

    def test_empty_observation_content_still_completes(self):
        observations = (
            _observation(label="", value="", notes="", metadata={}),
        )
        result = _evaluate(observations=observations)
        self.assertIs(result.status, ExperimentExecutionStatus.COMPLETED)

    def test_radically_different_observation_content_still_completes(self):
        observations = (
            _observation(
                observation_id="obs-x",
                label=" совершенно другой критерий",
                value="的不是数字",
                notes="semantically unrelated content",
                metadata={"nested": {"deep": [1, 2, 3]}},
            ),
        )
        result = _evaluate(observations=observations)
        self.assertIs(result.status, ExperimentExecutionStatus.COMPLETED)


class TestPlanSemanticsDoNotMatter(unittest.TestCase):
    def test_required_flag_does_not_affect_status(self):
        plan_true = _plan(required=True)
        plan_false = _plan(required=False)
        for plan in (plan_true, plan_false):
            empty = _evaluate(plan=plan, observations=())
            self.assertIs(empty.status, ExperimentExecutionStatus.INCONCLUSIVE)
            one = _evaluate(plan=plan, observations=(_observation(),))
            self.assertIs(one.status, ExperimentExecutionStatus.COMPLETED)

    def test_success_criteria_do_not_affect_status(self):
        plan_a = _plan(success_criteria=())
        plan_b = _plan(success_criteria=("criterion one", "criterion two", "criterion three"))
        observations = (_observation(),)
        self.assertIs(
            _evaluate(plan=plan_a, observations=observations).status,
            ExperimentExecutionStatus.COMPLETED,
        )
        self.assertIs(
            _evaluate(plan=plan_b, observations=observations).status,
            ExperimentExecutionStatus.COMPLETED,
        )

    def test_procedure_does_not_affect_status(self):
        plan_a = _plan(procedure=())
        plan_b = _plan(procedure=("single step",))
        observations = (_observation(),)
        self.assertEqual(
            _evaluate(plan=plan_a, observations=observations).status,
            _evaluate(plan=plan_b, observations=observations).status,
        )

    def test_hypothesis_does_not_affect_status(self):
        plan_a = _plan(hypothesis="Hypothesis A")
        plan_b = _plan(hypothesis="A completely different hypothesis B")
        observations = (_observation(),)
        self.assertEqual(
            _evaluate(plan=plan_a, observations=observations).status,
            _evaluate(plan=plan_b, observations=observations).status,
        )


class TestCallerValuePreservation(unittest.TestCase):
    def test_conclusion_preserved_exactly(self):
        result = _evaluate(
            observations=(_observation(),),
            conclusion="The workflow reduced observable manual steps.",
        )
        self.assertEqual(
            result.conclusion, "The workflow reduced observable manual steps."
        )
        empty = _evaluate(observations=(), conclusion="")
        self.assertEqual(empty.conclusion, "")

    def test_notes_preserved_exactly(self):
        result = _evaluate(
            observations=(_observation(),), notes="Manual offline observation."
        )
        self.assertEqual(result.notes, "Manual offline observation.")
        empty = _evaluate(observations=(), notes="")
        self.assertEqual(empty.notes, "")

    def test_raw_time_values_accepted_and_preserved(self):
        result = _evaluate(
            observations=(_observation(),),
            started_at="not-a-timestamp",
            completed_at=None,
        )
        self.assertEqual(result.started_at, "not-a-timestamp")
        self.assertIsNone(result.completed_at)

    def test_candidate_id_comes_from_plan_verbatim(self):
        plan = _plan(candidate_id="cand-special-999")
        result = _evaluate(plan=plan, observations=(_observation(),))
        self.assertEqual(result.candidate_id, "cand-special-999")


class TestIdentityPreservation(unittest.TestCase):
    def test_plan_identity_fully_preserved(self):
        plan = _plan()
        procedure = plan.procedure
        success_criteria = plan.success_criteria
        result = _evaluate(plan=plan, observations=(_observation(),))
        self.assertIs(result.plan, plan)
        self.assertIs(result.plan.procedure, procedure)
        self.assertIs(result.plan.success_criteria, success_criteria)

    def test_observation_identity_fully_preserved(self):
        observation = _observation()
        metadata = observation.metadata
        observations = (observation,)
        result = _evaluate(observations=observations)
        self.assertIs(result.observations, observations)
        self.assertIs(result.observations[0], observation)
        self.assertIs(result.observations[0].metadata, metadata)


class TestInputImmutability(unittest.TestCase):
    def test_plan_and_observations_unchanged_after_evaluation(self):
        plan = _plan()
        observation = _observation()
        metadata = observation.metadata
        observations = (observation,)

        _evaluate(plan=plan, observations=observations)

        self.assertEqual(plan.experiment_id, "cand-123:experiment")
        self.assertEqual(plan.candidate_id, "cand-123")
        self.assertEqual(
            plan.hypothesis,
            "Testing Example AI tool produces an observable practical result",
        )
        self.assertEqual(
            plan.procedure,
            (
                "Define the expected result and baseline",
                "Run the described approach in a controlled test",
                "Record the observable outcome",
                "Compare the outcome with the expected result",
            ),
        )
        self.assertEqual(
            plan.success_criteria,
            (
                "The procedure can be completed as described",
                "The outcome is observable and can support a practical conclusion",
            ),
        )
        self.assertIs(plan.required, True)
        self.assertEqual(observation.observation_id, "obs-1")
        self.assertEqual(observation.label, "manual_steps")
        self.assertEqual(observation.value, "3")
        self.assertEqual(observation.notes, "Observed during offline test")
        self.assertIs(observation.metadata, metadata)


class TestDeterminism(unittest.TestCase):
    def test_repeated_calls_produce_equal_results(self):
        kwargs = dict(
            plan=_plan(),
            observations=(_observation(),),
            started_at="2026-09-19T17:00:00+00:00",
            completed_at="2026-09-19T17:30:00+00:00",
            conclusion="conclusion",
            notes="notes",
        )
        first = evaluate_experiment_execution(**kwargs)
        second = evaluate_experiment_execution(**kwargs)
        self.assertEqual(first, second)


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees for the evaluator module
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


class TestEvaluatorStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _module_tree()
        cls.ids = _module_ids(cls.tree)
        cls.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_exactly_one_module_level_function(self):
        functions = [
            node for node in self.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(
            [f.name for f in functions], ["evaluate_experiment_execution"]
        )

    def test_all_is_exactly_evaluator_function(self):
        assigns = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        ]
        self.assertEqual(len(assigns), 1)
        values = [elt.value for elt in assigns[0].value.elts]
        self.assertEqual(values, ["evaluate_experiment_execution"])

    def test_construction_shape(self):
        result_calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ExperimentExecutionResult"
        ]
        plan_calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ExperimentPlan"
        ]
        observation_calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ExperimentObservation"
        ]
        self.assertEqual(len(result_calls), 1)
        self.assertEqual(plan_calls, [])
        self.assertEqual(observation_calls, [])

    def test_plan_field_access_boundary(self):
        accessed = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "plan"
        }
        self.assertEqual(accessed, {"candidate_id"})

    def test_no_observation_attribute_access(self):
        accessed = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in ("observation", "record")
        }
        self.assertEqual(accessed, set())

    def test_status_via_truthiness_not_len(self):
        self.assertNotIn("len(", self.source)

    def test_status_vocabulary_boundary(self):
        referenced = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ExperimentExecutionStatus"
        }
        self.assertEqual(referenced, {"COMPLETED", "INCONCLUSIVE"})

    def test_no_semantic_claim_identifiers(self):
        forbidden_tokens = (
            "criterion_passed",
            "criteria_met",
            "success_count",
            "passed",
            "failed_criterion",
            "hypothesis_proven",
            "hypothesis_true",
        )
        leaks = [token for token in forbidden_tokens if token in self.source]
        self.assertEqual(leaks, [])

    def test_no_forbidden_imports_or_references(self):
        forbidden = {
            # Generation sources.
            "datetime", "time", "uuid", "hashlib", "random",
            # Strategy / research / package coupling.
            "StrategistPlan", "ContentCandidate", "ContentFormat",
            "ContentCluster", "TargetPlatform",
            "ResearchRequirement", "EvidenceRecord", "ResearchExecutionResult",
            "ContentPackageV2", "PackageArtifact", "PackageStage",
            "QualityState", "PublicationState",
            "attach_package_artifact", "transition_package_stage",
            # Filesystem / network / process.
            "os", "pathlib", "subprocess", "requests", "httpx", "urllib",
            "socket",
            # Persistence / config / DB.
            "StateService", "Config", "sqlite3",
            # Social / publishing integrations.
            "publisher", "copywriter", "editor", "designer",
            "telegram", "x_client", "vk_client", "pinterest_client",
            # Serialization / validation / mutation helpers.
            "to_dict", "from_dict", "serialize", "deserialize", "as_dict",
            "validate", "sorted", "copy", "deepcopy", "ValueError",
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


if __name__ == "__main__":
    unittest.main()
