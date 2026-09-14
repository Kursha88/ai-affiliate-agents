"""Step 15A — Strategist 2.0 domain contracts (StrategistInput / StrategistPlan).

Tests use real existing types from src.domain.strategy. For the
StrategistInput identity/frozen behavior tests a bare
``object.__new__(ContentCandidate)`` is used, so no unrelated nested
objects (DiscoveryCandidate, VerificationResult, ...) are required.
"""

import ast
import dataclasses
import unittest
from pathlib import Path
from typing import Tuple, get_type_hints

from src.domain.strategy import (
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
from src.domain.strategist import StrategistInput, StrategistPlan

MODULE_PATH = Path("src/domain/strategist.py")

SELECTED_PLATFORMS: Tuple[TargetPlatform, ...] = (
    TargetPlatform.TELEGRAM,
    TargetPlatform.X,
    TargetPlatform.LINKEDIN,
)
STRUCTURE: Tuple[str, ...] = ("hook", "body", "cta")


def make_plan(**overrides) -> StrategistPlan:
    """Build a valid StrategistPlan with real enum values (no defaults)."""
    values = {
        "candidate_id": "cand-1",
        "topic": "Open-source coding agent",
        "content_cluster": ContentCluster.VIBE_CODING,
        "content_format": ContentFormat.PRACTICAL_GUIDE,
        "target_platforms": SELECTED_PLATFORMS,
        "research_required": False,
        "experiment_required": False,
        "angle": "hands-on with a free open-source agent",
        "hook": "Your IDE just got an agent",
        "objective": "teach the reader to try it today",
        "cta": "Try it yourself",
        "cta_link": "https://example.com/repo",
        "tone": "practical",
        "structure": STRUCTURE,
        "language": "ru",
        "mode": "growth",
    }
    values.update(overrides)
    return StrategistPlan(**values)


class TestStrategistInput(unittest.TestCase):
    """Tests 1-7: StrategistInput contract."""

    def setUp(self):
        # object.__new__ per spec: identity/frozen behavior without
        # constructing unrelated nested objects.
        self.candidate = object.__new__(ContentCandidate)
        self.input_obj = StrategistInput(content_candidate=self.candidate)

    # 1
    def test_is_dataclass(self):
        self.assertTrue(dataclasses.is_dataclass(StrategistInput))

    # 2
    def test_is_frozen(self):
        # Frozen dataclasses raise on ANY attribute assignment, including
        # non-field attributes, via their generated __setattr__.
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.input_obj._probe = 1
        # The declared field is equally locked (see test 6).
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.input_obj.content_candidate = None  # type: ignore[misc]

    # 3
    def test_exactly_one_field(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(StrategistInput)],
            ["content_candidate"],
        )

    # 4
    def test_annotation_is_content_candidate(self):
        self.assertIs(
            get_type_hints(StrategistInput)["content_candidate"], ContentCandidate
        )

    # 5
    def test_preserves_candidate_identity(self):
        self.assertIs(self.input_obj.content_candidate, self.candidate)

    # 6
    def test_cannot_reassign_content_candidate(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.input_obj.content_candidate = object.__new__(ContentCandidate)

    # 7
    def test_no_defaults(self):
        for f in dataclasses.fields(StrategistInput):
            self.assertEqual(
                f.default,
                dataclasses.MISSING,
                f"field {f.name} must have no default",
            )
            self.assertEqual(
                f.default_factory,
                dataclasses.MISSING,
                f"field {f.name} must have no default_factory",
            )


class TestStrategistPlan(unittest.TestCase):
    """Tests 8-40: StrategistPlan contract."""

    def setUp(self):
        self.plan = make_plan()

    # 8
    def test_is_dataclass(self):
        self.assertTrue(dataclasses.is_dataclass(StrategistPlan))

    # 9
    def test_is_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.plan._probe = 1

    # 10
    def test_field_order_exact(self):
        self.assertEqual(
            [f.name for f in dataclasses.fields(StrategistPlan)],
            [
                "candidate_id",
                "topic",
                "content_cluster",
                "content_format",
                "target_platforms",
                "research_required",
                "experiment_required",
                "angle",
                "hook",
                "objective",
                "cta",
                "cta_link",
                "tone",
                "structure",
                "language",
                "mode",
            ],
        )

    # 11-26: annotations, one subTest per field.
    def test_field_annotations(self):
        hints = get_type_hints(StrategistPlan)
        expected = {
            "candidate_id": str,
            "topic": str,
            "content_cluster": ContentCluster,
            "content_format": ContentFormat,
            "target_platforms": Tuple[TargetPlatform, ...],
            "research_required": bool,
            "experiment_required": bool,
            "angle": str,
            "hook": str,
            "objective": str,
            "cta": str,
            "cta_link": str,
            "tone": str,
            "structure": Tuple[str, ...],
            "language": str,
            "mode": str,
        }
        for name, annotation in expected.items():
            with self.subTest(field=name):
                self.assertEqual(hints[name], annotation)

    # 27
    def test_no_field_has_default(self):
        for f in dataclasses.fields(StrategistPlan):
            with self.subTest(field=f.name):
                self.assertEqual(f.default, dataclasses.MISSING)
                self.assertEqual(f.default_factory, dataclasses.MISSING)

    # 28
    def test_accepts_real_cluster_unchanged(self):
        for cluster in ContentCluster:
            with self.subTest(cluster=cluster):
                plan = make_plan(content_cluster=cluster)
                self.assertIs(plan.content_cluster, cluster)

    # 29
    def test_accepts_real_format_unchanged(self):
        for fmt in ContentFormat:
            with self.subTest(format=fmt):
                plan = make_plan(content_format=fmt)
                self.assertIs(plan.content_format, fmt)

    # 30
    def test_accepts_platform_tuple_unchanged(self):
        platforms = (
            TargetPlatform.TELEGRAM,
            TargetPlatform.PINTEREST,
            TargetPlatform.YOUTUBE_SHORTS,
        )
        plan = make_plan(target_platforms=platforms)
        self.assertEqual(plan.target_platforms, platforms)

    # 31
    def test_platform_tuple_identity_and_order_preserved(self):
        platforms = (
            TargetPlatform.X,
            TargetPlatform.TELEGRAM,  # deliberately not enum-declaration order
        )
        plan = make_plan(target_platforms=platforms)
        self.assertIs(plan.target_platforms, platforms)
        self.assertEqual(
            plan.target_platforms, (TargetPlatform.X, TargetPlatform.TELEGRAM)
        )

    # 32
    def test_structure_tuple_order_preserved(self):
        structure = ("z-section", "a-section", "m-section")
        plan = make_plan(structure=structure)
        self.assertEqual(plan.structure, ("z-section", "a-section", "m-section"))

    # 33
    def test_research_required_preserved(self):
        self.assertIs(make_plan(research_required=True).research_required, True)
        self.assertIs(make_plan(research_required=False).research_required, False)

    # 34
    def test_experiment_required_preserved(self):
        self.assertIs(make_plan(experiment_required=True).experiment_required, True)
        self.assertIs(make_plan(experiment_required=False).experiment_required, False)

    # 35
    def test_string_fields_preserved_exactly(self):
        strings = {
            "topic": "Тема с unicode ✨",
            "angle": "угол  <>&",
            "hook": "хук 🚀",
            "objective": "objective /:@#",
            "cta": "CTA",
            "cta_link": "https://example.com/cta?x=1#frag",
            "tone": "tone",
            "language": "ru",
            "mode": "mode",
        }
        plan = make_plan(**strings)
        for name, value in strings.items():
            with self.subTest(field=name):
                self.assertEqual(getattr(plan, name), value)

    # 36-40: frozen reassignment guards.
    def test_cannot_reassign_fields(self):
        cases = {
            "candidate_id": "other-id",           # 36
            "content_format": ContentFormat.WORKFLOW,  # 37
            "target_platforms": (),               # 38
            "angle": "other-angle",               # 39
            "structure": (),                      # 40
        }
        for name, value in cases.items():
            with self.subTest(field=name):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(self.plan, name, value)


class TestStructuralBoundaries(unittest.TestCase):
    """Tests 41-50: AST/introspection structural guarantees."""

    @classmethod
    def setUpClass(cls):
        cls.source = MODULE_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _imported_names(self):
        names = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    module = ".".join([""] * node.level) + module
                names.add(module)
        return names

    # 41
    def test_all_exports_exact(self):
        import src.domain.strategist as module

        self.assertEqual(
            list(module.__all__),
            ["StrategistInput", "StrategistPlan"],
        )

    # 42
    def test_no_enum_classes(self):
        enum_bases = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ClassDef)
            and any(
                (isinstance(b, ast.Name) and "Enum" in b.id)
                or (isinstance(b, ast.Attribute) and "Enum" in b.attr)
                for b in node.bases
            )
        ]
        self.assertEqual(enum_bases, [])

    # 43
    def test_exactly_two_public_classes(self):
        classes = [
            node.name
            for node in self.tree.body
            if isinstance(node, ast.ClassDef)
        ]
        self.assertEqual(classes, ["StrategistInput", "StrategistPlan"])

    # 44
    def test_no_post_init(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                defined = [f.name for f in node.body if isinstance(f, ast.FunctionDef)]
                self.assertNotIn("__post_init__", defined)

    # 45
    def test_no_to_dict(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                defined = [f.name for f in node.body if isinstance(f, ast.FunctionDef)]
                self.assertNotIn("to_dict", defined)

    # 46
    def test_no_from_dict(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                defined = [f.name for f in node.body if isinstance(f, ast.FunctionDef)]
                self.assertNotIn("from_dict", defined)

    # 47
    def test_no_forbidden_utility_imports(self):
        banned = {"datetime", "random", "os", "pathlib", "yaml", "requests"}
        self.assertEqual(self._imported_names() & banned, set())

    # 48
    def test_no_app_forbidden_imports(self):
        banned = {
            "Config",
            "StateService",
            "src.main",
            "src.agents",
        }
        imported = self._imported_names()
        for banned_name in banned:
            self.assertNotIn(banned_name, imported)

        # Also ban any import from the strategist agent module directly.
        modules = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name)
        self.assertEqual(
            modules & {"src.agents.strategist", "src.core.config"}, set()
        )

    # 49
    def test_no_mapping_or_generation_functions(self):
        banned_names = {
            "build_input",
            "map_candidate",
            "build_plan",
            "generate_cta",
            "generate_hook",
            "choose_format",
            "choose_platform",
            "to_plan",
            "from_candidate",
        }
        # No free functions at all in a contracts module.
        funcs = [
            node.name
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(funcs, [])

        # No methods on either dataclass (no dataclass-generated code is
        # written by hand, so none should exist in source).
        method_names = [
            item.name
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ClassDef)
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(method_names, [])

    # 50
    def test_no_mutable_list_annotations(self):
        source_no_strings = ast.unparse(self.tree)
        self.assertNotIn("List[", source_no_strings)
        self.assertNotIn("list[", source_no_strings)
        hints = get_type_hints(StrategistInput)
        hints.update(get_type_hints(StrategistPlan))
        for name, annotation in hints.items():
            self.assertNotEqual(
                getattr(annotation, "__origin__", None), list,
                f"field {name} must not be a mutable list",
            )


if __name__ == "__main__":
    unittest.main()
