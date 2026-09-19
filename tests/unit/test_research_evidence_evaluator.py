"""Step 17C unit tests: deterministic offline research evidence evaluator.

Covers the exact requirement-to-evidence kind compatibility policy,
satisfaction by DISTINCT evidence_id count, duplicate-ID non-inflation,
cross-requirement evidence reuse, optional requirements, zero/negative
minimum_items, deterministic notes in original requirement order, tuple
identity and input immutability, caller value preservation, the status
vocabulary boundary (only COMPLETED/INSUFFICIENT), and structural AST
guarantees including field access boundaries on requirements and evidence.
"""

import ast
import unittest
from pathlib import Path

from src.domain.research_execution import (
    EvidenceKind,
    EvidenceRecord,
    ResearchExecutionResult,
    ResearchExecutionStatus,
    ResearchRequirement,
    ResearchRequirementKind,
    RequirementOrigin,
)
from src.research.research_evidence_evaluator import evaluate_research_execution

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "research"
    / "research_evidence_evaluator.py"
)

STARTED_AT = "2026-09-19T16:00:00+00:00"
COMPLETED_AT = "2026-09-19T16:30:00+00:00"


def _requirement(requirement_id="req-1", **overrides) -> ResearchRequirement:
    defaults = dict(
        kind=ResearchRequirementKind.COMPARISON_TARGET,
        origin=RequirementOrigin.CONTENT_FORMAT,
        query="Find one credible comparison target",
        minimum_items=1,
        required=True,
    )
    defaults.update(overrides)
    return ResearchRequirement(requirement_id=requirement_id, **defaults)


def _evidence(evidence_id="evidence-1", kind=EvidenceKind.COMPARISON_TARGET, **overrides):
    defaults = dict(
        title="Alternative Tool",
        source_url="https://example.com/alternative",
        source_name="Example",
        captured_at="2026-09-19T16:00:00+00:00",
        summary="A credible comparison target.",
        metadata={"source": "test"},
    )
    defaults.update(overrides)
    return EvidenceRecord(evidence_id=evidence_id, kind=kind, **defaults)


def _evaluate(requirements=(), evidence=(), **overrides):
    params = dict(
        candidate_id="cand-123",
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )
    params.update(overrides)
    return evaluate_research_execution(
        requirements=requirements, evidence=evidence, **params
    )


class TestBasicCompleted(unittest.TestCase):
    def test_single_matching_evidence_completes(self):
        requirement = _requirement()
        requirements = (requirement,)
        evidence = (_evidence(),)
        result = _evaluate(requirements=requirements, evidence=evidence)
        self.assertIsInstance(result, ResearchExecutionResult)
        self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
        self.assertEqual(result.notes, "")
        self.assertEqual(result.candidate_id, "cand-123")
        self.assertEqual(result.started_at, STARTED_AT)
        self.assertEqual(result.completed_at, COMPLETED_AT)
        self.assertIs(result.requirements, requirements)
        self.assertIs(result.evidence, evidence)


class TestBasicInsufficient(unittest.TestCase):
    def test_non_matching_evidence_kind_is_insufficient(self):
        requirement = _requirement()
        evidence = (_evidence(kind=EvidenceKind.SUPPORTING_SOURCE),)
        result = _evaluate(requirements=(requirement,), evidence=evidence)
        self.assertIs(result.status, ResearchExecutionStatus.INSUFFICIENT)
        self.assertEqual(result.notes, "Unsatisfied required requirements: req-1")


class TestAllKindPolicies(unittest.TestCase):
    ALL_KINDS = tuple(EvidenceKind)

    def test_primary_source_policy(self):
        satisfying = {
            EvidenceKind.PRIMARY_SOURCE,
            EvidenceKind.DOCUMENTATION,
            EvidenceKind.REPOSITORY,
        }
        for kind in self.ALL_KINDS:
            with self.subTest(kind=kind.value):
                requirement = _requirement(
                    requirement_id="req-1",
                    kind=ResearchRequirementKind.PRIMARY_SOURCE,
                    origin=RequirementOrigin.SELECT_FLAG,
                )
                result = _evaluate(
                    requirements=(requirement,), evidence=(_evidence(kind=kind),)
                )
                if kind in satisfying:
                    self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
                else:
                    self.assertIs(result.status, ResearchExecutionStatus.INSUFFICIENT)

    def test_supporting_evidence_policy_accepts_every_kind(self):
        for kind in self.ALL_KINDS:
            with self.subTest(kind=kind.value):
                requirement = _requirement(
                    requirement_id="req-1",
                    kind=ResearchRequirementKind.SUPPORTING_EVIDENCE,
                )
                result = _evaluate(
                    requirements=(requirement,), evidence=(_evidence(kind=kind),)
                )
                self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)

    def test_comparison_target_policy_is_exact(self):
        for kind in self.ALL_KINDS:
            with self.subTest(kind=kind.value):
                requirement = _requirement(
                    requirement_id="req-1",
                    kind=ResearchRequirementKind.COMPARISON_TARGET,
                )
                result = _evaluate(
                    requirements=(requirement,), evidence=(_evidence(kind=kind),)
                )
                if kind is EvidenceKind.COMPARISON_TARGET:
                    self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
                else:
                    self.assertIs(result.status, ResearchExecutionStatus.INSUFFICIENT)

    def test_counterpoint_policy_is_exact(self):
        for kind in self.ALL_KINDS:
            with self.subTest(kind=kind.value):
                requirement = _requirement(
                    requirement_id="req-1",
                    kind=ResearchRequirementKind.COUNTERPOINT,
                )
                result = _evaluate(
                    requirements=(requirement,), evidence=(_evidence(kind=kind),)
                )
                if kind is EvidenceKind.COUNTERPOINT:
                    self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
                else:
                    self.assertIs(result.status, ResearchExecutionStatus.INSUFFICIENT)

    def test_implementation_details_policy(self):
        satisfying = {EvidenceKind.DOCUMENTATION, EvidenceKind.REPOSITORY}
        for kind in self.ALL_KINDS:
            with self.subTest(kind=kind.value):
                requirement = _requirement(
                    requirement_id="req-1",
                    kind=ResearchRequirementKind.IMPLEMENTATION_DETAILS,
                )
                result = _evaluate(
                    requirements=(requirement,), evidence=(_evidence(kind=kind),)
                )
                if kind in satisfying:
                    self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
                else:
                    self.assertIs(result.status, ResearchExecutionStatus.INSUFFICIENT)

    def test_real_world_example_policy_is_exact(self):
        for kind in self.ALL_KINDS:
            with self.subTest(kind=kind.value):
                requirement = _requirement(
                    requirement_id="req-1",
                    kind=ResearchRequirementKind.REAL_WORLD_EXAMPLE,
                )
                result = _evaluate(
                    requirements=(requirement,), evidence=(_evidence(kind=kind),)
                )
                if kind is EvidenceKind.REAL_WORLD_EXAMPLE:
                    self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
                else:
                    self.assertIs(result.status, ResearchExecutionStatus.INSUFFICIENT)


class TestMinimumItems(unittest.TestCase):
    def test_three_distinct_items_satisfy_minimum_three(self):
        requirement = _requirement(
            requirement_id="req-1",
            kind=ResearchRequirementKind.SUPPORTING_EVIDENCE,
            minimum_items=3,
        )
        evidence = (
            _evidence("e1", EvidenceKind.SUPPORTING_SOURCE),
            _evidence("e2", EvidenceKind.DOCUMENTATION),
            _evidence("e3", EvidenceKind.REPOSITORY),
        )
        result = _evaluate(requirements=(requirement,), evidence=evidence)
        self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)

    def test_two_items_fail_minimum_three(self):
        requirement = _requirement(
            requirement_id="req-1",
            kind=ResearchRequirementKind.SUPPORTING_EVIDENCE,
            minimum_items=3,
        )
        evidence = (
            _evidence("e1", EvidenceKind.SUPPORTING_SOURCE),
            _evidence("e2", EvidenceKind.DOCUMENTATION),
        )
        result = _evaluate(requirements=(requirement,), evidence=evidence)
        self.assertIs(result.status, ResearchExecutionStatus.INSUFFICIENT)
        self.assertEqual(result.notes, "Unsatisfied required requirements: req-1")

    def test_duplicate_id_does_not_inflate_count(self):
        requirement = _requirement(
            requirement_id="req-1",
            kind=ResearchRequirementKind.SUPPORTING_EVIDENCE,
            minimum_items=3,
        )
        evidence = (
            _evidence("same-id", EvidenceKind.SUPPORTING_SOURCE, title="A"),
            _evidence("same-id", EvidenceKind.DOCUMENTATION, title="B"),
            _evidence("same-id", EvidenceKind.REPOSITORY, title="C"),
        )
        result = _evaluate(requirements=(requirement,), evidence=evidence)
        self.assertIs(result.status, ResearchExecutionStatus.INSUFFICIENT)
        self.assertEqual(result.notes, "Unsatisfied required requirements: req-1")

    def test_distinct_ids_with_identical_data_count_separately(self):
        requirement = _requirement(
            requirement_id="req-1",
            kind=ResearchRequirementKind.SUPPORTING_EVIDENCE,
            minimum_items=3,
        )
        evidence = (
            _evidence("e1"),
            _evidence("e2"),
            _evidence("e3"),
        )
        result = _evaluate(requirements=(requirement,), evidence=evidence)
        self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)

    def test_returned_evidence_preserves_duplicates(self):
        record_a = _evidence("e1", title="First copy")
        record_b = _evidence("e1", title="Second copy")
        evidence = (record_a, record_b)
        result = _evaluate(evidence=evidence)
        self.assertIs(result.evidence, evidence)
        self.assertEqual(len(result.evidence), 2)


class TestCrossRequirementReuse(unittest.TestCase):
    def test_one_record_satisfies_two_requirements(self):
        primary = _requirement(
            requirement_id="req-primary",
            kind=ResearchRequirementKind.PRIMARY_SOURCE,
        )
        supporting = _requirement(
            requirement_id="req-supporting",
            kind=ResearchRequirementKind.SUPPORTING_EVIDENCE,
        )
        evidence = (_evidence("doc-1", EvidenceKind.DOCUMENTATION),)
        result = _evaluate(
            requirements=(primary, supporting), evidence=evidence
        )
        self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
        self.assertEqual(result.notes, "")


class TestOriginDoesNotMatter(unittest.TestCase):
    def test_all_origins_match_identically(self):
        for origin in (
            RequirementOrigin.CONTENT_FORMAT,
            RequirementOrigin.SELECT_FLAG,
            RequirementOrigin.MANUAL,
        ):
            with self.subTest(origin=origin.value):
                requirement = _requirement(requirement_id="req-1", origin=origin)
                result = _evaluate(
                    requirements=(requirement,), evidence=(_evidence(),)
                )
                self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)

    def test_query_and_origin_do_not_change_outcome(self):
        base = _requirement(requirement_id="req-1")
        variant = _requirement(
            requirement_id="req-1",
            query="A completely different research objective",
            origin=RequirementOrigin.MANUAL,
        )
        evidence = (_evidence(),)
        result_base = _evaluate(requirements=(base,), evidence=evidence)
        result_variant = _evaluate(requirements=(variant,), evidence=evidence)
        self.assertIs(result_base.status, ResearchExecutionStatus.COMPLETED)
        self.assertIs(result_variant.status, ResearchExecutionStatus.COMPLETED)


class TestOptionalRequirements(unittest.TestCase):
    def test_unmet_optional_requirement_still_completes(self):
        requirement = _requirement(
            requirement_id="req-optional",
            minimum_items=10,
            required=False,
        )
        result = _evaluate(requirements=(requirement,), evidence=())
        self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
        self.assertEqual(result.notes, "")

    def test_mixed_optional_and_required(self):
        optional = _requirement(
            requirement_id="req-optional", minimum_items=10, required=False
        )
        required = _requirement(requirement_id="req-required", minimum_items=1)
        result_ok = _evaluate(
            requirements=(optional, required), evidence=(_evidence(),)
        )
        self.assertIs(result_ok.status, ResearchExecutionStatus.COMPLETED)
        self.assertEqual(result_ok.notes, "")

        result_bad = _evaluate(requirements=(optional, required), evidence=())
        self.assertIs(result_bad.status, ResearchExecutionStatus.INSUFFICIENT)
        self.assertEqual(
            result_bad.notes, "Unsatisfied required requirements: req-required"
        )


class TestEdgeSemantics(unittest.TestCase):
    def test_zero_requirements_completes_with_identity(self):
        requirements = ()
        evidence = ()
        result = _evaluate(requirements=requirements, evidence=evidence)
        self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
        self.assertEqual(result.notes, "")
        self.assertIs(result.requirements, requirements)
        self.assertIs(result.evidence, evidence)

    def test_zero_and_negative_minimums_auto_satisfied(self):
        zero = _requirement(requirement_id="req-zero", minimum_items=0)
        negative = _requirement(
            requirement_id="req-negative", minimum_items=-1
        )
        result = _evaluate(requirements=(zero, negative), evidence=())
        self.assertIs(result.status, ResearchExecutionStatus.COMPLETED)
        self.assertEqual(result.notes, "")

    def test_unsatisfied_order_preserved_not_sorted(self):
        req_a = _requirement(
            requirement_id="req-a",
            kind=ResearchRequirementKind.COMPARISON_TARGET,
        )
        req_b = _requirement(
            requirement_id="req-b",
            kind=ResearchRequirementKind.COUNTERPOINT,
            minimum_items=2,
        )
        req_c = _requirement(
            requirement_id="req-c",
            kind=ResearchRequirementKind.REAL_WORLD_EXAMPLE,
        )
        evidence = (
            _evidence("cp-1", EvidenceKind.COUNTERPOINT),
            _evidence("cp-2", EvidenceKind.COUNTERPOINT),
        )
        result = _evaluate(requirements=(req_a, req_b, req_c), evidence=evidence)
        self.assertIs(result.status, ResearchExecutionStatus.INSUFFICIENT)
        self.assertEqual(
            result.notes, "Unsatisfied required requirements: req-a, req-c"
        )

    def test_multiple_unsatisfied_same_kind_in_original_order(self):
        first = _requirement(
            requirement_id="req-first",
            kind=ResearchRequirementKind.COMPARISON_TARGET,
            origin=RequirementOrigin.CONTENT_FORMAT,
        )
        second = _requirement(
            requirement_id="req-second",
            kind=ResearchRequirementKind.COMPARISON_TARGET,
            origin=RequirementOrigin.SELECT_FLAG,
        )
        result = _evaluate(requirements=(first, second), evidence=())
        self.assertIs(result.status, ResearchExecutionStatus.INSUFFICIENT)
        self.assertEqual(
            result.notes,
            "Unsatisfied required requirements: req-first, req-second",
        )


class TestCallerValuePreservation(unittest.TestCase):
    def test_raw_caller_values_accepted_and_preserved(self):
        requirement = _requirement()
        evidence = (_evidence(),)
        result = _evaluate(
            requirements=(requirement,),
            evidence=evidence,
            candidate_id="",
            started_at="not-a-timestamp",
            completed_at=None,
        )
        self.assertEqual(result.candidate_id, "")
        self.assertEqual(result.started_at, "not-a-timestamp")
        self.assertIsNone(result.completed_at)


class TestNonMatchFieldsDoNotMatter(unittest.TestCase):
    def test_descriptive_evidence_fields_do_not_change_outcome(self):
        requirement = _requirement()
        plain = _evidence("same-id")
        radical = _evidence(
            "same-id",
            title="Totally different",
            source_url="https://other.example.org/thing?q=1",
            source_name="Elsewhere",
            captured_at="1999-12-31T23:59:59+00:00",
            summary="Nothing alike at all.",
            metadata={"entropy": "maximal", "nested": {"a": [1, 2, 3]}},
        )
        result_plain = _evaluate(requirements=(requirement,), evidence=(plain,))
        result_radical = _evaluate(requirements=(requirement,), evidence=(radical,))
        self.assertIs(result_plain.status, ResearchExecutionStatus.COMPLETED)
        self.assertIs(result_radical.status, ResearchExecutionStatus.COMPLETED)


class TestInputIdentityImmutability(unittest.TestCase):
    def test_inputs_preserved_by_identity_and_value(self):
        requirement = _requirement()
        record = _evidence()
        metadata = record.metadata
        requirements = (requirement,)
        evidence = (record,)

        result = _evaluate(requirements=requirements, evidence=evidence)

        self.assertIs(result.requirements, requirements)
        self.assertIs(result.evidence, evidence)
        self.assertIs(result.requirements[0], requirement)
        self.assertIs(result.evidence[0], record)
        self.assertIs(result.evidence[0].metadata, metadata)
        self.assertEqual(requirement.requirement_id, "req-1")
        self.assertIs(requirement.kind, ResearchRequirementKind.COMPARISON_TARGET)
        self.assertEqual(requirement.minimum_items, 1)
        self.assertIs(requirement.required, True)
        self.assertEqual(record.evidence_id, "evidence-1")
        self.assertIs(record.kind, EvidenceKind.COMPARISON_TARGET)


class TestDeterminism(unittest.TestCase):
    def test_repeated_calls_produce_equal_results(self):
        requirement = _requirement()
        evidence = (_evidence(),)
        kwargs = dict(
            candidate_id="cand-123",
            requirements=(requirement,),
            evidence=evidence,
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
        )
        first = evaluate_research_execution(**kwargs)
        second = evaluate_research_execution(**kwargs)
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

    def _policy_assignment(self):
        assignments = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_REQUIREMENT_EVIDENCE_POLICY"
                for t in node.targets
            )
        ]
        self.assertEqual(len(assignments), 1)
        return assignments[0].value

    def test_exactly_one_module_level_function(self):
        functions = [
            node for node in self.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(
            [f.name for f in functions], ["evaluate_research_execution"]
        )

    def test_all_is_exactly_evaluator_function(self):
        assigns = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        ]
        self.assertEqual(len(assigns), 1)
        values = [elt.value for elt in assigns[0].value.elts]
        self.assertEqual(values, ["evaluate_research_execution"])

    def test_policy_covers_every_requirement_kind_exactly_once(self):
        mapping = self._policy_assignment()
        keys = [
            key.attr for key in mapping.keys
            if isinstance(key, ast.Attribute)
            and isinstance(key.value, ast.Name)
            and key.value.id == "ResearchRequirementKind"
        ]
        self.assertEqual(
            sorted(keys), sorted(kind.name for kind in ResearchRequirementKind)
        )
        self.assertEqual(len(keys), len(set(keys)))

    def test_policy_values_are_tuple_literals(self):
        mapping = self._policy_assignment()
        for value in mapping.values:
            self.assertIsInstance(value, ast.Tuple)

    def test_direct_indexing_no_get_no_try(self):
        self.assertNotIn(".get(", self.source)
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.Try)

    def test_construction_shape(self):
        result_calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ResearchExecutionResult"
        ]
        requirement_calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ResearchRequirement"
        ]
        evidence_calls = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "EvidenceRecord"
        ]
        self.assertEqual(len(result_calls), 1)
        self.assertEqual(requirement_calls, [])
        self.assertEqual(evidence_calls, [])

    def test_no_forbidden_imports_or_references(self):
        forbidden = {
            # Generation sources.
            "datetime", "time", "uuid", "hashlib", "random",
            # Strategy / package coupling.
            "StrategistPlan", "ContentFormat", "ContentCluster",
            "ContentCandidate", "ContentPackageV2", "PackageArtifact",
            "PackageStage", "attach_package_artifact", "transition_package_stage",
            # Origin must not influence matching.
            "RequirementOrigin",
            # Filesystem / network / process.
            "os", "pathlib", "subprocess", "requests", "httpx", "urllib",
            "socket",
            # Persistence / config / DB.
            "StateService", "Config", "sqlite3",
            # Social / publishing integrations.
            "publisher", "copywriter", "editor", "designer",
            "telegram", "x_client", "vk_client", "pinterest_client",
            # Serialization / validation / sorting / mutation.
            "to_dict", "from_dict", "serialize", "deserialize", "as_dict",
            "validate", "sorted",
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

    def test_status_vocabulary_boundary(self):
        referenced = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ResearchExecutionStatus"
        }
        self.assertEqual(referenced, {"COMPLETED", "INSUFFICIENT"})

    def test_requirement_field_access_boundary(self):
        accessed = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "requirement"
        }
        self.assertEqual(
            accessed,
            {"kind", "minimum_items", "required", "requirement_id"},
        )

    def test_evidence_field_access_boundary(self):
        accessed = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "record"
        }
        self.assertEqual(accessed, {"kind", "evidence_id"})


if __name__ == "__main__":
    unittest.main()
