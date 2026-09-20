"""Tests for Stage 18D-A PlatformAdaptationInstruction domain contract."""

import ast
import dataclasses
import unittest
from dataclasses import FrozenInstanceError
from typing import Any, Mapping, Optional, Tuple

import src.domain.platform_adaptation as adaptation_module
from src.domain.platform_adaptation import (
    AdaptationContentKind,
    AdaptationSourceContent,
    PlatformAdaptationInstruction,
    PlatformAdaptationSpec,
    PlatformContentVariant,
)
from src.domain.strategy import TargetPlatform

MODULE_PATH = "src/domain/platform_adaptation.py"

MISSING = dataclasses.MISSING

EXPECTED_INSTRUCTION_FIELDS = [
    "candidate_id",
    "source_content_id",
    "platform",
    "content_kind",
    "source_language",
    "output_language",
    "requires_title",
    "allows_external_link",
    "max_characters",
    "structure",
    "tone",
    "source_title",
    "source_body",
    "source_cta",
    "source_cta_link",
    "metadata",
]

EXPECTED_SOURCE_FIELDS = [
    "content_id",
    "candidate_id",
    "title",
    "body",
    "cta",
    "cta_link",
    "language",
    "metadata",
]

EXPECTED_SPEC_FIELDS = [
    "platform",
    "content_kind",
    "max_characters",
    "requires_title",
    "allows_external_link",
    "structure",
    "tone",
]

EXPECTED_VARIANT_FIELDS = [
    "variant_id",
    "candidate_id",
    "source_content_id",
    "platform",
    "content_kind",
    "title",
    "body",
    "cta",
    "cta_link",
    "language",
    "metadata",
]


def _module_source() -> str:
    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _module_tree() -> ast.Module:
    return ast.parse(_module_source(), filename=MODULE_PATH)


def _make_instruction(**overrides):
    values = dict(
        candidate_id="cand-123",
        source_content_id="content-123",
        platform=TargetPlatform.TELEGRAM,
        content_kind=AdaptationContentKind.TEXT_POST,
        source_language="ru",
        output_language="ru",
        requires_title=True,
        allows_external_link=True,
        max_characters=None,
        structure=("hook", "context", "value", "cta"),
        tone="concise and practical",
        source_title="Canonical title",
        source_body="Canonical body",
        source_cta="Read more",
        source_cta_link="https://example.com",
        metadata={"source": "test"},
    )
    values.update(overrides)
    return PlatformAdaptationInstruction(**values)


class FieldContractTests(unittest.TestCase):
    def test_exact_field_contract(self):
        self.assertTrue(dataclasses.is_dataclass(PlatformAdaptationInstruction))
        fields = dataclasses.fields(PlatformAdaptationInstruction)
        self.assertEqual([f.name for f in fields], EXPECTED_INSTRUCTION_FIELDS)
        self.assertEqual(len(fields), 16)

    def test_all_fields_required(self):
        for field in dataclasses.fields(PlatformAdaptationInstruction):
            with self.subTest(field=field.name):
                self.assertIs(field.default, MISSING)
                self.assertIs(field.default_factory, MISSING)

    def test_frozen(self):
        self.assertTrue(PlatformAdaptationInstruction.__dataclass_params__.frozen)
        instruction = _make_instruction()
        with self.assertRaises(FrozenInstanceError):
            instruction.tone = "changed"


class ConstructionTests(unittest.TestCase):
    def test_representative_construction(self):
        instruction = _make_instruction()
        self.assertEqual(instruction.candidate_id, "cand-123")
        self.assertEqual(instruction.source_content_id, "content-123")
        self.assertIs(instruction.platform, TargetPlatform.TELEGRAM)
        self.assertIs(instruction.content_kind, AdaptationContentKind.TEXT_POST)
        self.assertEqual(instruction.source_language, "ru")
        self.assertEqual(instruction.output_language, "ru")
        self.assertTrue(instruction.requires_title)
        self.assertTrue(instruction.allows_external_link)
        self.assertIsNone(instruction.max_characters)
        self.assertEqual(instruction.structure, ("hook", "context", "value", "cta"))
        self.assertEqual(instruction.tone, "concise and practical")
        self.assertEqual(instruction.source_title, "Canonical title")
        self.assertEqual(instruction.source_body, "Canonical body")
        self.assertEqual(instruction.source_cta, "Read more")
        self.assertEqual(instruction.source_cta_link, "https://example.com")
        self.assertEqual(instruction.metadata, {"source": "test"})

    def test_metadata_identity(self):
        metadata = {
            "nested": {"x": 1},
            "items": [1, 2],
        }
        instruction = _make_instruction(metadata=metadata)
        self.assertIs(instruction.metadata, metadata)

    def test_structure_identity(self):
        structure = ("hook", "value", "cta")
        instruction = _make_instruction(structure=structure)
        self.assertIs(instruction.structure, structure)

    def test_empty_strings_allowed(self):
        instruction = _make_instruction(
            candidate_id="",
            source_content_id="",
            source_language="",
            output_language="",
            tone="",
            source_title="",
            source_body="",
            source_cta="",
            source_cta_link="",
        )
        self.assertEqual(instruction.candidate_id, "")
        self.assertEqual(instruction.source_content_id, "")
        self.assertEqual(instruction.source_language, "")
        self.assertEqual(instruction.output_language, "")
        self.assertEqual(instruction.tone, "")
        self.assertEqual(instruction.source_title, "")
        self.assertEqual(instruction.source_body, "")
        self.assertEqual(instruction.source_cta, "")
        self.assertEqual(instruction.source_cta_link, "")

    def test_max_characters_contract_only(self):
        for max_characters in (None, 0, -1, 1, 280, 3000, 999_999):
            with self.subTest(max_characters=max_characters):
                instruction = _make_instruction(max_characters=max_characters)
                self.assertEqual(instruction.max_characters, max_characters)

    def test_all_platforms_accepted(self):
        for platform in TargetPlatform:
            with self.subTest(platform=platform):
                instruction = _make_instruction(platform=platform)
                self.assertIs(instruction.platform, platform)

    def test_all_content_kinds_accepted(self):
        for content_kind in AdaptationContentKind:
            with self.subTest(content_kind=content_kind):
                instruction = _make_instruction(content_kind=content_kind)
                self.assertIs(instruction.content_kind, content_kind)

    def test_source_output_language_can_differ(self):
        instruction = _make_instruction(source_language="en", output_language="ru")
        self.assertEqual(instruction.source_language, "en")
        self.assertEqual(instruction.output_language, "ru")


class TypeAnnotationTests(unittest.TestCase):
    def test_exact_annotations(self):
        annotations = PlatformAdaptationInstruction.__annotations__
        self.assertIs(annotations["candidate_id"], str)
        self.assertIs(annotations["source_content_id"], str)
        self.assertIs(annotations["platform"], TargetPlatform)
        self.assertIs(annotations["content_kind"], AdaptationContentKind)
        self.assertIs(annotations["source_language"], str)
        self.assertIs(annotations["output_language"], str)
        self.assertIs(annotations["requires_title"], bool)
        self.assertIs(annotations["allows_external_link"], bool)
        self.assertEqual(annotations["max_characters"], Optional[int])
        self.assertEqual(annotations["structure"], Tuple[str, ...])
        self.assertIs(annotations["tone"], str)
        self.assertIs(annotations["source_title"], str)
        self.assertIs(annotations["source_body"], str)
        self.assertIs(annotations["source_cta"], str)
        self.assertIs(annotations["source_cta_link"], str)
        self.assertEqual(annotations["metadata"], Mapping[str, Any])


class ExistingContractRegressionTests(unittest.TestCase):
    def test_source_content_field_contract_unchanged(self):
        fields = dataclasses.fields(AdaptationSourceContent)
        self.assertEqual([f.name for f in fields], EXPECTED_SOURCE_FIELDS)
        self.assertTrue(AdaptationSourceContent.__dataclass_params__.frozen)

    def test_spec_field_contract_unchanged(self):
        fields = dataclasses.fields(PlatformAdaptationSpec)
        self.assertEqual([f.name for f in fields], EXPECTED_SPEC_FIELDS)
        self.assertTrue(PlatformAdaptationSpec.__dataclass_params__.frozen)

    def test_variant_field_contract_unchanged(self):
        fields = dataclasses.fields(PlatformContentVariant)
        self.assertEqual([f.name for f in fields], EXPECTED_VARIANT_FIELDS)
        self.assertTrue(PlatformContentVariant.__dataclass_params__.frozen)

    def test_enum_regression(self):
        self.assertEqual(
            [(member.name, member.value) for member in AdaptationContentKind],
            [
                ("TEXT_POST", "text_post"),
                ("SHORT_VIDEO_SCRIPT", "short_video_script"),
                ("PIN_COPY", "pin_copy"),
            ],
        )


class StructuralTests(unittest.TestCase):
    @staticmethod
    def _is_all_assignment(node) -> bool:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            return False
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != "__all__":
            return False
        value = node.value
        return (
            isinstance(value, ast.List)
            and all(
                isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                for elt in value.elts
            )
        )

    def _class_by_name(self, name):
        tree = _module_tree()
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == name:
                return node
        self.fail(f"class {name} not found")

    def test_exactly_one_enum_and_four_dataclasses(self):
        tree = _module_tree()
        class_defs = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        self.assertEqual(
            [c.name for c in class_defs],
            [
                "AdaptationContentKind",
                "AdaptationSourceContent",
                "PlatformAdaptationSpec",
                "PlatformContentVariant",
                "PlatformAdaptationInstruction",
            ],
        )
        enum_classes = [
            c
            for c in class_defs
            if any(
                isinstance(base, ast.Name) and base.id == "StrEnum"
                for base in c.bases
            )
        ]
        self.assertEqual([c.name for c in enum_classes], ["AdaptationContentKind"])

    def test_no_module_level_functions(self):
        tree = _module_tree()
        functions = [
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(functions, [])

    def test_exact_all(self):
        self.assertEqual(
            adaptation_module.__all__,
            [
                "AdaptationContentKind",
                "AdaptationSourceContent",
                "PlatformAdaptationSpec",
                "PlatformContentVariant",
                "PlatformAdaptationInstruction",
            ],
        )

    def test_no_new_imports_beyond_existing(self):
        tree = _module_tree()
        imports_from = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
        by_module = {n.module: [a.name for a in n.names] for n in imports_from}
        self.assertEqual(
            by_module,
            {
                "dataclasses": ["dataclass"],
                "enum": ["StrEnum"],
                "typing": ["Any", "Mapping", "Optional", "Tuple"],
                "src.domain.strategy": ["TargetPlatform"],
            },
        )
        self.assertEqual(
            [n for n in tree.body if isinstance(n, ast.Import)],
            [],
        )

    def test_no_forbidden_identifiers(self):
        tree = _module_tree()
        identifiers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
        for forbidden in (
            "StrategistPlan",
            "ContentCandidate",
            "ContentFormat",
            "ContentCluster",
            "ContentPackageV2",
            "PlatformVariantRef",
            "PackageStage",
            "QualityState",
            "PublicationState",
            "PackageArtifact",
            "ResearchExecutionResult",
            "ExperimentExecutionResult",
            "__post_init__",
            "ValueError",
            "TypeError",
            "to_dict",
            "from_dict",
            "serialize",
            "deserialize",
            "json",
            "pickle",
            "asdict",
            "model",
            "provider",
            "temperature",
            "max_tokens",
            "api_key",
            "openai",
            "anthropic",
            "datetime",
            "time",
            "uuid",
            "hashlib",
            "random",
            "os",
            "pathlib",
            "subprocess",
            "requests",
            "httpx",
            "urllib",
            "socket",
            "sqlite3",
            "StateService",
            "Config",
            "open",
            "print",
            "exec",
            "eval",
        ):
            self.assertNotIn(forbidden, identifiers)

    def test_instruction_has_no_output_result_variant_id_fields(self):
        instruction = self._class_by_name("PlatformAdaptationInstruction")
        assigned = set()
        for node in instruction.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                assigned.add(node.target.id)
        self.assertEqual(
            assigned,
            set(EXPECTED_INSTRUCTION_FIELDS),
        )

    def test_instruction_has_no_prompt_fields(self):
        instruction = self._class_by_name("PlatformAdaptationInstruction")
        body_source = ast.unparse(instruction)
        for token in ("prompt", "system_prompt", "user_prompt", "llm_prompt"):
            self.assertNotIn(token, body_source)

    def test_instruction_has_no_media_or_timestamp_or_package_fields(self):
        instruction = self._class_by_name("PlatformAdaptationInstruction")
        body_source = ast.unparse(instruction)
        for token in (
            "image",
            "video",
            "audio",
            "voiceover",
            "subtitle",
            "thumbnail",
            "media",
            "asset",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "package_id",
            "status",
            "execution_status",
            "adaptation_status",
        ):
            self.assertNotIn(token, body_source)

    def test_all_new_fields_required_structurally(self):
        instruction = self._class_by_name("PlatformAdaptationInstruction")
        for node in instruction.body:
            if isinstance(node, ast.AnnAssign):
                # A bare annotation (value is None) means no default and no
                # field(...) call with default/default_factory is possible.
                self.assertIsNone(node.value)


if __name__ == "__main__":
    unittest.main()
