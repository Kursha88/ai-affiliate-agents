"""Tests for Stage 18D-C platform adaptation execution domain contracts."""

import ast
import dataclasses
import unittest
from dataclasses import FrozenInstanceError
from typing import Any, Mapping

import src.domain.platform_adaptation_execution as execution_module
from src.domain.platform_adaptation import AdaptationContentKind
from src.domain.platform_adaptation_execution import (
    AdaptationExecutionStatus,
    PlatformAdaptationExecutionResult,
)
from src.domain.strategy import TargetPlatform

MODULE_PATH = "src/domain/platform_adaptation_execution.py"

MISSING = dataclasses.MISSING

EXPECTED_FIELDS = [
    "candidate_id",
    "source_content_id",
    "platform",
    "content_kind",
    "title",
    "body",
    "cta",
    "output_language",
    "status",
    "metadata",
]


def _module_source() -> str:
    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _module_tree() -> ast.Module:
    return ast.parse(_module_source(), filename=MODULE_PATH)


def _make_result(**overrides):
    values = dict(
        candidate_id="cand-123",
        source_content_id="content-123",
        platform=TargetPlatform.TELEGRAM,
        content_kind=AdaptationContentKind.TEXT_POST,
        title="Telegram title",
        body="Telegram body",
        cta="Read more",
        output_language="ru",
        status=AdaptationExecutionStatus.COMPLETED,
        metadata={"provider": "test"},
    )
    values.update(overrides)
    return PlatformAdaptationExecutionResult(**values)


class StatusEnumTests(unittest.TestCase):
    def test_declaration_order_exact(self):
        self.assertEqual(
            list(AdaptationExecutionStatus),
            [
                AdaptationExecutionStatus.COMPLETED,
                AdaptationExecutionStatus.FAILED,
                AdaptationExecutionStatus.MANUAL_REVIEW,
            ],
        )

    def test_values_exact(self):
        self.assertEqual(AdaptationExecutionStatus.COMPLETED.value, "completed")
        self.assertEqual(AdaptationExecutionStatus.FAILED.value, "failed")
        self.assertEqual(AdaptationExecutionStatus.MANUAL_REVIEW.value, "manual_review")

    def test_string_behavior(self):
        self.assertTrue(issubclass(AdaptationExecutionStatus, str))
        for member in AdaptationExecutionStatus:
            with self.subTest(member=member):
                self.assertIsInstance(member, str)
                self.assertEqual(str(member), member.value)


class FieldContractTests(unittest.TestCase):
    def test_exact_field_contract(self):
        self.assertTrue(dataclasses.is_dataclass(PlatformAdaptationExecutionResult))
        fields = dataclasses.fields(PlatformAdaptationExecutionResult)
        self.assertEqual([f.name for f in fields], EXPECTED_FIELDS)
        self.assertEqual(len(fields), 10)

    def test_all_fields_required(self):
        for field in dataclasses.fields(PlatformAdaptationExecutionResult):
            with self.subTest(field=field.name):
                self.assertIs(field.default, MISSING)
                self.assertIs(field.default_factory, MISSING)

    def test_frozen(self):
        self.assertTrue(PlatformAdaptationExecutionResult.__dataclass_params__.frozen)
        result = _make_result()
        with self.assertRaises(FrozenInstanceError):
            result.status = AdaptationExecutionStatus.FAILED


class ConstructionTests(unittest.TestCase):
    def test_representative_completed_result(self):
        metadata = {"provider": "test"}
        result = _make_result(metadata=metadata)
        self.assertEqual(result.candidate_id, "cand-123")
        self.assertEqual(result.source_content_id, "content-123")
        self.assertIs(result.platform, TargetPlatform.TELEGRAM)
        self.assertIs(result.content_kind, AdaptationContentKind.TEXT_POST)
        self.assertEqual(result.title, "Telegram title")
        self.assertEqual(result.body, "Telegram body")
        self.assertEqual(result.cta, "Read more")
        self.assertEqual(result.output_language, "ru")
        self.assertIs(result.status, AdaptationExecutionStatus.COMPLETED)
        self.assertIs(result.metadata, metadata)

    def test_failed_result_allows_text(self):
        result = _make_result(
            status=AdaptationExecutionStatus.FAILED,
            title="partial title",
            body="partial body",
            cta="partial cta",
        )
        self.assertIs(result.status, AdaptationExecutionStatus.FAILED)
        self.assertEqual(result.title, "partial title")
        self.assertEqual(result.body, "partial body")
        self.assertEqual(result.cta, "partial cta")

    def test_failed_result_allows_empty_text(self):
        result = _make_result(
            status=AdaptationExecutionStatus.FAILED,
            title="",
            body="",
            cta="",
        )
        self.assertEqual(result.title, "")
        self.assertEqual(result.body, "")
        self.assertEqual(result.cta, "")

    def test_manual_review_allows_empty_text(self):
        result = _make_result(
            status=AdaptationExecutionStatus.MANUAL_REVIEW,
            title="",
            body="",
            cta="",
        )
        self.assertIs(result.status, AdaptationExecutionStatus.MANUAL_REVIEW)
        self.assertEqual(result.title, "")
        self.assertEqual(result.body, "")
        self.assertEqual(result.cta, "")

    def test_completed_allows_empty_text(self):
        result = _make_result(
            status=AdaptationExecutionStatus.COMPLETED,
            title="",
            body="",
            cta="",
        )
        self.assertIs(result.status, AdaptationExecutionStatus.COMPLETED)
        self.assertEqual(result.title, "")
        self.assertEqual(result.body, "")
        self.assertEqual(result.cta, "")

    def test_empty_correlation_and_language_values(self):
        result = _make_result(
            candidate_id="",
            source_content_id="",
            output_language="",
        )
        self.assertEqual(result.candidate_id, "")
        self.assertEqual(result.source_content_id, "")
        self.assertEqual(result.output_language, "")

    def test_metadata_identity(self):
        metadata = {
            "nested": {"x": 1},
            "items": [1, 2],
        }
        result = _make_result(metadata=metadata)
        self.assertIs(result.metadata, metadata)

    def test_all_target_platforms_accepted(self):
        for platform in TargetPlatform:
            with self.subTest(platform=platform):
                result = _make_result(platform=platform)
                self.assertIs(result.platform, platform)

    def test_all_content_kinds_accepted(self):
        for content_kind in AdaptationContentKind:
            with self.subTest(content_kind=content_kind):
                result = _make_result(content_kind=content_kind)
                self.assertIs(result.content_kind, content_kind)

    def test_all_platform_content_kind_combinations_accepted(self):
        for platform in TargetPlatform:
            for content_kind in AdaptationContentKind:
                with self.subTest(platform=platform, content_kind=content_kind):
                    result = _make_result(platform=platform, content_kind=content_kind)
                    self.assertIs(result.platform, platform)
                    self.assertIs(result.content_kind, content_kind)

    def test_output_language_contract_only(self):
        for language in ("ru", "uk", "en", "", "xx"):
            with self.subTest(language=language):
                result = _make_result(output_language=language)
                self.assertEqual(result.output_language, language)

    def test_text_preserved_verbatim(self):
        result = _make_result(
            title="  TITLE  ",
            body="\nBODY\n",
            cta="\tCTA\t",
        )
        self.assertEqual(result.title, "  TITLE  ")
        self.assertEqual(result.body, "\nBODY\n")
        self.assertEqual(result.cta, "\tCTA\t")

    def test_status_values_independent_of_content(self):
        for status in AdaptationExecutionStatus:
            with self.subTest(status=status):
                result = _make_result(
                    status=status,
                    title="same title",
                    body="same body",
                    cta="same cta",
                )
                self.assertIs(result.status, status)
                self.assertEqual(result.title, "same title")


class TypeAnnotationTests(unittest.TestCase):
    def test_exact_annotations(self):
        annotations = PlatformAdaptationExecutionResult.__annotations__
        self.assertIs(annotations["candidate_id"], str)
        self.assertIs(annotations["source_content_id"], str)
        self.assertIs(annotations["platform"], TargetPlatform)
        self.assertIs(annotations["content_kind"], AdaptationContentKind)
        self.assertIs(annotations["title"], str)
        self.assertIs(annotations["body"], str)
        self.assertIs(annotations["cta"], str)
        self.assertIs(annotations["output_language"], str)
        self.assertIs(annotations["status"], AdaptationExecutionStatus)
        self.assertEqual(annotations["metadata"], Mapping[str, Any])


class StructuralTests(unittest.TestCase):
    def test_exactly_two_classes_in_declaration_order(self):
        tree = _module_tree()
        class_defs = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        self.assertEqual(
            [c.name for c in class_defs],
            [
                "AdaptationExecutionStatus",
                "PlatformAdaptationExecutionResult",
            ],
        )

    def test_exactly_one_strenum_and_one_dataclass(self):
        tree = _module_tree()
        class_defs = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        enum_classes = [
            c
            for c in class_defs
            if any(
                isinstance(base, ast.Name) and base.id == "StrEnum"
                for base in c.bases
            )
        ]
        self.assertEqual([c.name for c in enum_classes], ["AdaptationExecutionStatus"])
        status_class = enum_classes[0]
        status_assignments = [
            node
            for node in status_class.body
            if isinstance(node, ast.Assign)
        ]
        self.assertEqual(
            [(t.id, node.value.value) for node in status_assignments for t in node.targets],
            [
                ("COMPLETED", "completed"),
                ("FAILED", "failed"),
                ("MANUAL_REVIEW", "manual_review"),
            ],
        )

    def test_zero_functions_anywhere(self):
        tree = _module_tree()
        function_nodes = [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(function_nodes, [])

    def test_exact_all(self):
        self.assertEqual(
            execution_module.__all__,
            [
                "AdaptationExecutionStatus",
                "PlatformAdaptationExecutionResult",
            ],
        )

    def test_exact_import_surface(self):
        tree = _module_tree()
        imports_from = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
        by_module = {n.module: [a.name for a in n.names] for n in imports_from}
        self.assertEqual(
            by_module,
            {
                "dataclasses": ["dataclass"],
                "enum": ["StrEnum"],
                "typing": ["Any", "Mapping"],
                "src.domain.platform_adaptation": ["AdaptationContentKind"],
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
            "AdaptationSourceContent",
            "PlatformAdaptationSpec",
            "PlatformAdaptationInstruction",
            "PlatformContentVariant",
            "ResearchExecutionResult",
            "ExperimentExecutionResult",
            "ResearchRequirement",
            "EvidenceRecord",
            "ContentPackageV2",
            "PlatformVariantRef",
            "PackageStage",
            "QualityState",
            "PublicationState",
            "PackageArtifact",
            "__post_init__",
            "ValueError",
            "TypeError",
            "validate",
            "to_dict",
            "from_dict",
            "serialize",
            "deserialize",
            "json",
            "pickle",
            "asdict",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "package_id",
            "variant_id",
            "cta_link",
            "source_title",
            "source_body",
            "source_cta",
            "source_cta_link",
            "source_language",
            "requires_title",
            "allows_external_link",
            "max_characters",
            "structure",
            "tone",
            "prompt",
            "model",
            "provider",
            "temperature",
            "max_tokens",
            "api_key",
            "raw_response",
            "raw_output",
            "completion",
            "response_text",
            "provider_payload",
            "image",
            "video",
            "audio",
            "voiceover",
            "subtitle",
            "thumbnail",
            "media",
            "asset",
            "openai",
            "anthropic",
            "gemini",
            "groq",
            "llm",
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

    def test_result_field_annotations_exactly(self):
        tree = _module_tree()
        result_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "PlatformAdaptationExecutionResult"
        )
        assigned = [
            node.target.id
            for node in result_class.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        ]
        self.assertEqual(assigned, EXPECTED_FIELDS)
        for node in result_class.body:
            if isinstance(node, ast.AnnAssign):
                self.assertIsNone(node.value)

    def test_module_body_composition(self):
        tree = _module_tree()
        for node in tree.body:
            if self._is_all_assignment(node):
                continue
            allowed = (
                ast.Expr,
                ast.Import,
                ast.ImportFrom,
                ast.ClassDef,
            )
            self.assertIsInstance(node, allowed)

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


if __name__ == "__main__":
    unittest.main()
