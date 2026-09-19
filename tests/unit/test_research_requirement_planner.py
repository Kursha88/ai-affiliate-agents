"""Step 17B unit tests: deterministic research requirement / experiment planner.

Covers the exact per-format research policy table, the critical
COMPARISON-without-research-flag production case, SELECT_FLAG behavior,
deterministic ordering and IDs, no cross-origin deduplication, the
experiment trigger policy with exact plan strings, determinism, planner
independence, StrategistPlan immutability, and structural AST guarantees
(field access boundary, exact policy map, no side-effect coupling).
"""

import ast
import unittest
from pathlib import Path

from src.domain.research_execution import (
    ExperimentPlan,
    RequirementOrigin,
    ResearchRequirement,
    ResearchRequirementKind,
)
from src.domain.strategy import ContentCluster, ContentFormat, TargetPlatform
from src.domain.strategist import StrategistPlan
from src.research.research_requirement_planner import (
    plan_experiment,
    plan_research_requirements,
)

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "research"
    / "research_requirement_planner.py"
)


def _plan(**overrides) -> StrategistPlan:
    """Fresh real StrategistPlan per call (never mutate an existing one)."""
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


# (format, kind, query, minimum_items) for every intrinsic policy;
# formats with None policy are asserted to produce zero requirements.
INTRINSIC_POLICY = {
    ContentFormat.BREAKING_NEWS: (
        ResearchRequirementKind.PRIMARY_SOURCE,
        "Confirm the story against the authoritative primary source",
        1,
    ),
    ContentFormat.TOOL_DISCOVERY: (
        ResearchRequirementKind.PRIMARY_SOURCE,
        "Find authoritative product documentation or repository for the selected tool",
        1,
    ),
    ContentFormat.PRACTICAL_GUIDE: (
        ResearchRequirementKind.IMPLEMENTATION_DETAILS,
        "Find concrete implementation details needed to reproduce the guide",
        1,
    ),
    ContentFormat.COMPARISON: (
        ResearchRequirementKind.COMPARISON_TARGET,
        "Find one credible alternative to compare with the selected topic",
        1,
    ),
    ContentFormat.EXPERIMENT: None,
    ContentFormat.WORKFLOW: (
        ResearchRequirementKind.IMPLEMENTATION_DETAILS,
        "Find concrete implementation details needed to reproduce the workflow",
        1,
    ),
    ContentFormat.PROMPT: None,
    ContentFormat.CASE_STUDY: (
        ResearchRequirementKind.REAL_WORLD_EXAMPLE,
        "Find one concrete real-world example relevant to the selected topic",
        1,
    ),
    ContentFormat.OPINION_ANALYSIS: (
        ResearchRequirementKind.COUNTERPOINT,
        "Find one credible counterpoint or materially different perspective",
        1,
    ),
    ContentFormat.ROUNDUP: (
        ResearchRequirementKind.SUPPORTING_EVIDENCE,
        "Find at least three credible items suitable for the roundup",
        3,
    ),
}


class TestAllFormatPolicies(unittest.TestCase):
    def test_every_format_produces_exact_intrinsic_requirement(self):
        for content_format, policy in INTRINSIC_POLICY.items():
            with self.subTest(format=content_format.value):
                plan = _plan(content_format=content_format, research_required=False)
                requirements = plan_research_requirements(plan)
                if policy is None:
                    self.assertEqual(requirements, ())
                    continue
                kind, query, minimum_items = policy
                self.assertEqual(len(requirements), 1)
                requirement = requirements[0]
                self.assertIs(requirement.kind, kind)
                self.assertIs(requirement.origin, RequirementOrigin.CONTENT_FORMAT)
                self.assertEqual(requirement.query, query)
                self.assertEqual(requirement.minimum_items, minimum_items)
                self.assertIs(requirement.required, True)
                self.assertEqual(
                    requirement.requirement_id,
                    f"cand-123:format:{kind.value}",
                )


class TestCriticalComparisonCase(unittest.TestCase):
    def test_comparison_without_research_flag_still_requires_target(self):
        plan = _plan(content_format=ContentFormat.COMPARISON, research_required=False)
        requirements = plan_research_requirements(plan)
        self.assertEqual(len(requirements), 1)
        requirement = requirements[0]
        self.assertIs(requirement.kind, ResearchRequirementKind.COMPARISON_TARGET)
        self.assertIs(requirement.origin, RequirementOrigin.CONTENT_FORMAT)
        self.assertEqual(requirement.minimum_items, 1)
        self.assertIs(requirement.required, True)
        self.assertEqual(requirement.requirement_id, "cand-123:format:comparison_target")
        self.assertEqual(
            requirement.query,
            "Find one credible alternative to compare with the selected topic",
        )


class TestSelectFlagBehavior(unittest.TestCase):
    def test_prompt_without_flag_produces_empty_tuple(self):
        plan = _plan(content_format=ContentFormat.PROMPT, research_required=False)
        self.assertEqual(plan_research_requirements(plan), ())

    def test_prompt_with_flag_produces_exactly_one_select_requirement(self):
        plan = _plan(content_format=ContentFormat.PROMPT, research_required=True)
        requirements = plan_research_requirements(plan)
        self.assertEqual(len(requirements), 1)
        requirement = requirements[0]
        self.assertIs(requirement.kind, ResearchRequirementKind.SUPPORTING_EVIDENCE)
        self.assertIs(requirement.origin, RequirementOrigin.SELECT_FLAG)
        self.assertEqual(
            requirement.query,
            "Gather additional credible evidence for the selected topic",
        )
        self.assertEqual(requirement.minimum_items, 1)
        self.assertIs(requirement.required, True)
        self.assertEqual(
            requirement.requirement_id, "cand-123:select:supporting_evidence"
        )

    def test_format_requirement_comes_before_select_requirement(self):
        plan = _plan(content_format=ContentFormat.COMPARISON, research_required=True)
        requirements = plan_research_requirements(plan)
        self.assertEqual(len(requirements), 2)
        self.assertIs(requirements[0].kind, ResearchRequirementKind.COMPARISON_TARGET)
        self.assertIs(requirements[0].origin, RequirementOrigin.CONTENT_FORMAT)
        self.assertEqual(
            requirements[0].requirement_id, "cand-123:format:comparison_target"
        )
        self.assertIs(requirements[1].kind, ResearchRequirementKind.SUPPORTING_EVIDENCE)
        self.assertIs(requirements[1].origin, RequirementOrigin.SELECT_FLAG)
        self.assertEqual(
            requirements[1].requirement_id, "cand-123:select:supporting_evidence"
        )

    def test_roundup_same_kind_different_origin_not_deduplicated(self):
        plan = _plan(content_format=ContentFormat.ROUNDUP, research_required=True)
        requirements = plan_research_requirements(plan)
        self.assertEqual(len(requirements), 2)
        self.assertIs(requirements[0].kind, ResearchRequirementKind.SUPPORTING_EVIDENCE)
        self.assertIs(requirements[0].origin, RequirementOrigin.CONTENT_FORMAT)
        self.assertEqual(requirements[0].minimum_items, 3)
        self.assertIs(requirements[1].kind, ResearchRequirementKind.SUPPORTING_EVIDENCE)
        self.assertIs(requirements[1].origin, RequirementOrigin.SELECT_FLAG)
        self.assertEqual(requirements[1].minimum_items, 1)
        self.assertIsNot(requirements[0], requirements[1])


class TestDeterminism(unittest.TestCase):
    def test_research_requirements_equal_across_calls(self):
        plan = _plan(content_format=ContentFormat.ROUNDUP, research_required=True)
        first = plan_research_requirements(plan)
        second = plan_research_requirements(plan)
        self.assertEqual(first, second)
        self.assertEqual(
            [r.requirement_id for r in first],
            ["cand-123:format:supporting_evidence", "cand-123:select:supporting_evidence"],
        )

    def test_experiment_plan_equal_across_calls(self):
        plan = _plan(experiment_required=True)
        first = plan_experiment(plan)
        second = plan_experiment(plan)
        self.assertEqual(first, second)


class TestCandidateIdPreservation(unittest.TestCase):
    def test_ids_use_candidate_id_verbatim(self):
        plan = _plan(
            candidate_id="cand-special-999",
            content_format=ContentFormat.COMPARISON,
            research_required=True,
            experiment_required=True,
        )
        requirements = plan_research_requirements(plan)
        self.assertEqual(
            [r.requirement_id for r in requirements],
            [
                "cand-special-999:format:comparison_target",
                "cand-special-999:select:supporting_evidence",
            ],
        )
        experiment = plan_experiment(plan)
        self.assertEqual(experiment.experiment_id, "cand-special-999:experiment")
        self.assertEqual(experiment.candidate_id, "cand-special-999")


class TestExperimentPlanning(unittest.TestCase):
    def test_experiment_format_is_intrinsically_planned(self):
        plan = _plan(
            content_format=ContentFormat.EXPERIMENT, experiment_required=False
        )
        experiment = plan_experiment(plan)
        self.assertIsInstance(experiment, ExperimentPlan)
        self.assertEqual(experiment.experiment_id, "cand-123:experiment")
        self.assertEqual(experiment.candidate_id, "cand-123")
        self.assertIs(experiment.required, True)
        self.assertEqual(
            experiment.hypothesis,
            "Testing Example AI tool produces an observable practical result",
        )
        self.assertEqual(
            experiment.procedure,
            (
                "Define the expected result and baseline",
                "Run the described approach in a controlled test",
                "Record the observable outcome",
                "Compare the outcome with the expected result",
            ),
        )
        self.assertEqual(
            experiment.success_criteria,
            (
                "The procedure can be completed as described",
                "The outcome is observable and can support a practical conclusion",
            ),
        )

    def test_explicit_experiment_flag_on_non_experiment_format(self):
        plan = _plan(content_format=ContentFormat.WORKFLOW, experiment_required=True)
        self.assertIsInstance(plan_experiment(plan), ExperimentPlan)

    def test_no_experiment_when_neither_flag_nor_format(self):
        plan = _plan(content_format=ContentFormat.WORKFLOW, experiment_required=False)
        self.assertIsNone(plan_experiment(plan))

    def test_both_triggers_produce_exactly_one_plan(self):
        plan = _plan(
            content_format=ContentFormat.EXPERIMENT, experiment_required=True
        )
        experiment = plan_experiment(plan)
        self.assertIsInstance(experiment, ExperimentPlan)
        self.assertEqual(experiment.experiment_id, "cand-123:experiment")

    def test_experiment_format_produces_zero_intrinsic_research_requirements(self):
        plan = _plan(
            content_format=ContentFormat.EXPERIMENT,
            research_required=True,
            experiment_required=True,
        )
        requirements = plan_research_requirements(plan)
        self.assertEqual(len(requirements), 1)
        self.assertIs(requirements[0].origin, RequirementOrigin.SELECT_FLAG)
        self.assertIs(
            requirements[0].kind, ResearchRequirementKind.SUPPORTING_EVIDENCE
        )
        self.assertIsInstance(plan_experiment(plan), ExperimentPlan)


class TestPlanningIndependence(unittest.TestCase):
    def test_cluster_does_not_affect_planning(self):
        plan_a = _plan(content_cluster=ContentCluster.AI_TOOLS)
        plan_b = _plan(content_cluster=ContentCluster.FREE_AI)
        self.assertEqual(
            plan_research_requirements(plan_a),
            plan_research_requirements(plan_b),
        )
        self.assertEqual(plan_experiment(plan_a), plan_experiment(plan_b))

    def test_target_platforms_do_not_affect_planning(self):
        plan_a = _plan(target_platforms=(TargetPlatform.TELEGRAM,))
        plan_b = _plan(
            target_platforms=(
                TargetPlatform.TIKTOK,
                TargetPlatform.PINTEREST,
                TargetPlatform.YOUTUBE_SHORTS,
            )
        )
        self.assertEqual(
            plan_research_requirements(plan_a),
            plan_research_requirements(plan_b),
        )
        self.assertEqual(plan_experiment(plan_a), plan_experiment(plan_b))

    def test_unused_strategist_fields_do_not_affect_planning(self):
        plan_a = _plan(
            angle="angle-a",
            hook="hook-a",
            objective="objective-a",
            cta="cta-a",
            cta_link="https://example.com/a",
            tone="tone-a",
            structure=("a",),
            language="en",
            mode="expert",
        )
        plan_b = _plan(
            angle="angle-b",
            hook="hook-b",
            objective="objective-b",
            cta="cta-b",
            cta_link="https://example.com/b",
            tone="tone-b",
            structure=("b", "c"),
            language="ru",
            mode="growth",
        )
        self.assertEqual(
            plan_research_requirements(plan_a),
            plan_research_requirements(plan_b),
        )
        self.assertEqual(plan_experiment(plan_a), plan_experiment(plan_b))

    def test_topic_only_affects_experiment_hypothesis(self):
        plan_a = _plan(topic="Tool A", experiment_required=True)
        plan_b = _plan(topic="Tool B", experiment_required=True)
        self.assertEqual(
            plan_research_requirements(plan_a),
            plan_research_requirements(plan_b),
        )
        experiment_a = plan_experiment(plan_a)
        experiment_b = plan_experiment(plan_b)
        self.assertEqual(experiment_a.experiment_id, experiment_b.experiment_id)
        self.assertEqual(experiment_a.procedure, experiment_b.procedure)
        self.assertEqual(
            experiment_a.success_criteria, experiment_b.success_criteria
        )
        self.assertEqual(
            experiment_a.hypothesis,
            "Testing Tool A produces an observable practical result",
        )
        self.assertEqual(
            experiment_b.hypothesis,
            "Testing Tool B produces an observable practical result",
        )
        self.assertNotEqual(experiment_a.hypothesis, experiment_b.hypothesis)


class TestStrategistPlanImmutability(unittest.TestCase):
    def test_planner_functions_do_not_mutate_the_plan(self):
        plan = _plan(
            content_format=ContentFormat.ROUNDUP,
            research_required=True,
            experiment_required=True,
        )
        plan_ref = plan
        platforms_ref = plan.target_platforms
        structure_ref = plan.structure

        plan_research_requirements(plan)
        plan_experiment(plan)

        self.assertIs(plan, plan_ref)
        self.assertIs(plan.target_platforms, platforms_ref)
        self.assertIs(plan.structure, structure_ref)
        self.assertEqual(plan.candidate_id, "cand-123")
        self.assertEqual(plan.topic, "Example AI tool")
        self.assertIs(plan.content_format, ContentFormat.ROUNDUP)
        self.assertIs(plan.research_required, True)
        self.assertIs(plan.experiment_required, True)
        self.assertEqual(plan.angle, "angle")
        self.assertEqual(plan.hook, "hook")
        self.assertEqual(plan.objective, "objective")
        self.assertEqual(plan.cta, "cta")
        self.assertEqual(plan.cta_link, "https://example.com/tool")
        self.assertEqual(plan.tone, "tone")
        self.assertEqual(plan.structure, ("context", "body", "cta"))
        self.assertEqual(plan.language, "ru")
        self.assertEqual(plan.mode, "growth")


# ──────────────────────────────────────────────────────────────────────
# Structural AST guarantees for the planner module
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


class TestPlannerStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _module_tree()
        cls.ids = _module_ids(cls.tree)
        cls.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_exactly_two_module_level_functions(self):
        functions = [
            node for node in self.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(
            [f.name for f in functions],
            ["plan_research_requirements", "plan_experiment"],
        )

    def test_all_is_exactly_two_functions(self):
        assigns = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
        ]
        self.assertEqual(len(assigns), 1)
        values = [elt.value for elt in assigns[0].value.elts]
        self.assertEqual(values, ["plan_research_requirements", "plan_experiment"])

    def test_policy_map_exists_and_covers_every_format_exactly_once(self):
        assignments = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_FORMAT_RESEARCH_POLICY"
                for t in node.targets
            )
        ]
        self.assertEqual(len(assignments), 1)
        mapping = assignments[0].value
        self.assertIsInstance(mapping, ast.Dict)
        keys = [
            key.attr for key in mapping.keys
            if isinstance(key, ast.Attribute)
            and isinstance(key.value, ast.Name)
            and key.value.id == "ContentFormat"
        ]
        self.assertEqual(
            sorted(keys), sorted(fmt.name for fmt in ContentFormat)
        )
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), 10)

    def test_experiment_and_prompt_map_to_none(self):
        assignments = [
            node for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_FORMAT_RESEARCH_POLICY"
                for t in node.targets
            )
        ]
        mapping = assignments[0].value
        none_keys = {
            key.attr
            for key, value in zip(mapping.keys, mapping.values)
            if isinstance(key, ast.Attribute)
            and isinstance(value, ast.Constant)
            and value.value is None
        }
        self.assertEqual(none_keys, {"EXPERIMENT", "PROMPT"})

    def test_no_get_calls_or_fallback_branches(self):
        self.assertNotIn(".get(", self.source)
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.Try)

    def test_no_forbidden_imports_or_references(self):
        forbidden = {
            # Generation sources.
            "datetime", "time", "uuid", "hashlib", "random",
            # Package coupling (17E owns integration).
            "ContentPackageV2", "PackageArtifact", "PackageStage",
            "QualityState", "PublicationState",
            "attach_package_artifact", "transition_package_stage",
            # Upstream aggregate not allowed as input.
            "ContentCandidate",
            # Filesystem / network / process.
            "os", "pathlib", "subprocess", "requests", "httpx", "urllib",
            "socket",
            # Persistence / config / DB.
            "StateService", "Config", "sqlite3",
            # Social / publishing integrations.
            "publisher", "copywriter", "editor", "designer",
            "telegram", "x_client", "vk_client", "pinterest_client",
            # Serialization / validation / manual origin.
            "to_dict", "from_dict", "serialize", "deserialize", "as_dict",
            "MANUAL",
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

    def test_no_loops(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, (ast.For, ast.AsyncFor))
            self.assertNotIsInstance(
                node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
            )

    def test_field_access_boundary(self):
        """Production logic touches only the five allowed StrategistPlan attrs."""
        allowed = {
            "candidate_id", "topic", "content_format",
            "research_required", "experiment_required",
        }
        accessed = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "strategist_plan"
        }
        self.assertTrue(accessed, "planner must access the strategist plan")
        self.assertEqual(accessed - allowed, set())

    def test_research_requirement_construction_shape(self):
        constructions = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ResearchRequirement"
        ]
        self.assertEqual(len(constructions), 2)

    def test_experiment_plan_construction_shape(self):
        constructions = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ExperimentPlan"
        ]
        self.assertEqual(len(constructions), 1)


if __name__ == "__main__":
    unittest.main()
