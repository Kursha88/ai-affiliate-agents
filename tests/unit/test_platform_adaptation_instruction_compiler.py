"""Tests for Stage 18D-B deterministic platform adaptation instruction compiler."""

import ast
import inspect
import unittest
from typing import Any, Mapping

import src.content.platform_adaptation_instruction_compiler as compiler_module
from src.content.platform_adaptation_instruction_compiler import (
    compile_platform_adaptation_instruction,
)
from src.content.platform_adaptation_policy import get_platform_adaptation_spec
from src.domain.platform_adaptation import (
    AdaptationContentKind,
    AdaptationSourceContent,
    PlatformAdaptationInstruction,
    PlatformAdaptationSpec,
)
from src.domain.strategy import TargetPlatform

MODULE_PATH = "src/content/platform_adaptation_instruction_compiler.py"


def _module_source() -> str:
    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _module_tree() -> ast.Module:
    return ast.parse(_module_source(), filename=MODULE_PATH)


def _make_source(**overrides):
    values = dict(
        content_id="content-123",
        candidate_id="cand-123",
        title="Canonical title",
        body="Canonical body",
        cta="Canonical CTA",
        cta_link="https://example.com/tool",
        language="ru",
        metadata={"source": "canonical"},
    )
    values.update(overrides)
    return AdaptationSourceContent(**values)


def _make_custom_spec(**overrides):
    values = dict(
        platform=TargetPlatform.X,
        content_kind=AdaptationContentKind.TEXT_POST,
        max_characters=None,
        requires_title=True,
        allows_external_link=True,
        structure=("body",),
        tone="neutral",
    )
    values.update(overrides)
    return PlatformAdaptationSpec(**values)


class RealSpecCompilationTests(unittest.TestCase):
    def setUp(self):
        self.source = _make_source()

    def test_telegram_compilation(self):
        metadata = {"compiler": "test"}
        instruction = compile_platform_adaptation_instruction(
            self.source,
            get_platform_adaptation_spec(TargetPlatform.TELEGRAM),
            output_language="uk",
            metadata=metadata,
        )
        self.assertIsInstance(instruction, PlatformAdaptationInstruction)
        self.assertEqual(instruction.candidate_id, "cand-123")
        self.assertEqual(instruction.source_content_id, "content-123")
        self.assertIs(instruction.platform, TargetPlatform.TELEGRAM)
        self.assertIs(instruction.content_kind, AdaptationContentKind.TEXT_POST)
        self.assertEqual(instruction.source_language, "ru")
        self.assertEqual(instruction.output_language, "uk")
        self.assertIs(instruction.requires_title, True)
        self.assertIs(instruction.allows_external_link, True)
        self.assertIsNone(instruction.max_characters)
        self.assertEqual(instruction.structure, ("hook", "context", "value", "cta"))
        self.assertEqual(instruction.tone, "concise and practical")
        self.assertEqual(instruction.source_title, "Canonical title")
        self.assertEqual(instruction.source_body, "Canonical body")
        self.assertEqual(instruction.source_cta, "Canonical CTA")
        self.assertEqual(instruction.source_cta_link, "https://example.com/tool")
        self.assertIs(instruction.metadata, metadata)

    def test_all_real_platforms(self):
        for platform in TargetPlatform:
            with self.subTest(platform=platform):
                spec = get_platform_adaptation_spec(platform)
                instruction = compile_platform_adaptation_instruction(
                    self.source,
                    spec,
                    output_language="ru",
                    metadata={},
                )
                self.assertIs(instruction.platform, spec.platform)
                self.assertIs(instruction.content_kind, spec.content_kind)
                self.assertIs(instruction.requires_title, spec.requires_title)
                self.assertIs(instruction.allows_external_link, spec.allows_external_link)
                self.assertEqual(instruction.max_characters, spec.max_characters)
                self.assertIs(instruction.structure, spec.structure)
                self.assertEqual(instruction.tone, spec.tone)


class SnapshotExactnessTests(unittest.TestCase):
    def test_source_snapshot_exactness(self):
        source = _make_source(
            content_id=" content ",
            candidate_id="\tID\n",
            title="  TITLE  ",
            body="\nBODY\n",
            cta=" CTA ",
            cta_link="not-a-url",
            language="xx",
        )
        instruction = compile_platform_adaptation_instruction(
            source,
            _make_custom_spec(),
            output_language="ru",
            metadata={},
        )
        self.assertEqual(instruction.source_content_id, " content ")
        self.assertEqual(instruction.candidate_id, "\tID\n")
        self.assertEqual(instruction.source_title, "  TITLE  ")
        self.assertEqual(instruction.source_body, "\nBODY\n")
        self.assertEqual(instruction.source_cta, " CTA ")
        self.assertEqual(instruction.source_cta_link, "not-a-url")
        self.assertEqual(instruction.source_language, "xx")

    def test_output_language_exact(self):
        source = _make_source(language="ru")
        english = compile_platform_adaptation_instruction(
            source, _make_custom_spec(), output_language="en", metadata={}
        )
        self.assertEqual(english.output_language, "en")
        empty = compile_platform_adaptation_instruction(
            source, _make_custom_spec(), output_language="", metadata={}
        )
        self.assertEqual(empty.output_language, "")
        self.assertEqual(empty.source_language, "ru")

    def test_same_language_allowed(self):
        instruction = compile_platform_adaptation_instruction(
            _make_source(language="ru"),
            _make_custom_spec(),
            output_language="ru",
            metadata={},
        )
        self.assertEqual(instruction.output_language, "ru")

    def test_title_preserved_when_policy_says_no_title(self):
        source = _make_source(title="Canonical title")
        spec = get_platform_adaptation_spec(TargetPlatform.X)
        self.assertFalse(spec.requires_title)
        instruction = compile_platform_adaptation_instruction(
            source, spec, output_language="ru", metadata={}
        )
        self.assertEqual(instruction.source_title, "Canonical title")

    def test_link_preserved_when_policy_says_no_link(self):
        source = _make_source(cta_link="https://example.com")
        spec = get_platform_adaptation_spec(TargetPlatform.REDDIT)
        self.assertFalse(spec.allows_external_link)
        instruction = compile_platform_adaptation_instruction(
            source, spec, output_language="ru", metadata={}
        )
        self.assertEqual(instruction.source_cta_link, "https://example.com")

    def test_max_characters_copied_only(self):
        long_body = "y" * 10_000
        source = _make_source(body=long_body)
        for max_characters in (None, 0, -1, 1, 999_999):
            with self.subTest(max_characters=max_characters):
                spec = _make_custom_spec(max_characters=max_characters)
                instruction = compile_platform_adaptation_instruction(
                    source, spec, output_language="ru", metadata={}
                )
                self.assertEqual(instruction.max_characters, max_characters)
                self.assertEqual(instruction.source_body, long_body)


class CustomSpecTests(unittest.TestCase):
    def test_custom_spec_passthrough(self):
        source = _make_source()
        spec = _make_custom_spec(
            platform=TargetPlatform.TELEGRAM,
            content_kind=AdaptationContentKind.PIN_COPY,
            max_characters=-99,
            requires_title=False,
            allows_external_link=False,
            structure=("custom",),
            tone="custom-tone",
        )
        instruction = compile_platform_adaptation_instruction(
            source, spec, output_language="uk", metadata={}
        )
        self.assertIs(instruction.platform, TargetPlatform.TELEGRAM)
        self.assertIs(instruction.content_kind, AdaptationContentKind.PIN_COPY)
        self.assertEqual(instruction.max_characters, -99)
        self.assertIs(instruction.requires_title, False)
        self.assertIs(instruction.allows_external_link, False)
        self.assertEqual(instruction.structure, ("custom",))
        self.assertEqual(instruction.tone, "custom-tone")

    def test_structure_identity(self):
        structure = ("a", "b", "c")
        spec = _make_custom_spec(structure=structure)
        instruction = compile_platform_adaptation_instruction(
            _make_source(), spec, output_language="ru", metadata={}
        )
        self.assertIs(instruction.structure, structure)
        self.assertIs(instruction.structure, spec.structure)


class MetadataTests(unittest.TestCase):
    def test_metadata_identity(self):
        metadata = {
            "nested": {"x": 1},
            "items": [1, 2],
        }
        instruction = compile_platform_adaptation_instruction(
            _make_source(), _make_custom_spec(), output_language="ru", metadata=metadata
        )
        self.assertIs(instruction.metadata, metadata)

    def test_source_metadata_isolation(self):
        source = _make_source(
            metadata={"source_only": True, "collision": "source"},
        )
        caller_metadata = {
            "instruction_only": True,
            "collision": "instruction",
        }
        instruction = compile_platform_adaptation_instruction(
            source, _make_custom_spec(), output_language="ru", metadata=caller_metadata
        )
        self.assertIs(instruction.metadata, caller_metadata)
        self.assertEqual(
            instruction.metadata,
            {"instruction_only": True, "collision": "instruction"},
        )
        self.assertNotIn("source_only", instruction.metadata)


class VariationAndDeterminismTests(unittest.TestCase):
    def test_source_text_variation_changes_instruction(self):
        base = _make_source(
            title="Title A", body="Body A", cta="CTA A", cta_link="A-link"
        )
        other = _make_source(
            title="Title B", body="Body B", cta="CTA B", cta_link="B-link"
        )
        spec = _make_custom_spec()
        first = compile_platform_adaptation_instruction(
            base, spec, output_language="ru", metadata={}
        )
        second = compile_platform_adaptation_instruction(
            other, spec, output_language="ru", metadata={}
        )
        self.assertEqual(first.source_title, "Title A")
        self.assertEqual(second.source_title, "Title B")
        self.assertEqual(first.source_body, "Body A")
        self.assertEqual(second.source_body, "Body B")
        self.assertEqual(first.source_cta, "CTA A")
        self.assertEqual(second.source_cta, "CTA B")
        self.assertEqual(first.source_cta_link, "A-link")
        self.assertEqual(second.source_cta_link, "B-link")
        self.assertNotEqual(first, second)

    def test_source_metadata_does_not_affect_instruction(self):
        source_a = _make_source(metadata={"variant": "a"})
        source_b = _make_source(metadata={"variant": "b"})
        spec = _make_custom_spec()
        caller_metadata = {"fixed": True}
        first = compile_platform_adaptation_instruction(
            source_a, spec, output_language="ru", metadata=caller_metadata
        )
        second = compile_platform_adaptation_instruction(
            source_b, spec, output_language="ru", metadata=caller_metadata
        )
        self.assertEqual(first, second)

    def test_same_input_equality(self):
        source = _make_source()
        spec = _make_custom_spec()
        metadata = {"same": True}
        first = compile_platform_adaptation_instruction(
            source, spec, output_language="uk", metadata=metadata
        )
        second = compile_platform_adaptation_instruction(
            source, spec, output_language="uk", metadata=metadata
        )
        self.assertEqual(first, second)
        self.assertIsNot(first, second)

    def test_input_immutability(self):
        metadata = {"m": 1}
        source = _make_source(metadata=metadata)
        spec = _make_custom_spec(structure=("a", "b"))
        source_ref = source
        source_metadata_ref = source.metadata
        spec_structure_ref = spec.structure
        compile_platform_adaptation_instruction(
            source, spec, output_language="ru", metadata=metadata
        )
        self.assertIs(source, source_ref)
        self.assertIs(source.metadata, source_metadata_ref)
        self.assertIs(spec.structure, spec_structure_ref)
        self.assertEqual(source, _make_source(metadata=metadata))

    def test_empty_values_accepted(self):
        source = _make_source(
            content_id="",
            candidate_id="",
            title="",
            body="",
            cta="",
            cta_link="",
            language="",
            metadata={},
        )
        instruction = compile_platform_adaptation_instruction(
            source, _make_custom_spec(), output_language="", metadata={}
        )
        self.assertEqual(instruction.candidate_id, "")
        self.assertEqual(instruction.source_content_id, "")
        self.assertEqual(instruction.source_language, "")
        self.assertEqual(instruction.output_language, "")
        self.assertEqual(instruction.source_title, "")
        self.assertEqual(instruction.source_body, "")
        self.assertEqual(instruction.source_cta, "")
        self.assertEqual(instruction.source_cta_link, "")
        self.assertEqual(instruction.metadata, {})


class TypeAnnotationTests(unittest.TestCase):
    def test_function_annotations_exact(self):
        annotations = compile_platform_adaptation_instruction.__annotations__
        self.assertIs(annotations["source"], AdaptationSourceContent)
        self.assertIs(annotations["spec"], PlatformAdaptationSpec)
        self.assertIs(annotations["output_language"], str)
        self.assertEqual(annotations["metadata"], Mapping[str, Any])
        self.assertIs(annotations["return"], PlatformAdaptationInstruction)


class StructuralTests(unittest.TestCase):
    FORBIDDEN_IDENTIFIERS = (
        "TargetPlatform",
        "AdaptationContentKind",
        "PlatformContentVariant",
        "get_platform_adaptation_spec",
        "get_platform_adaptation_specs",
        "build_platform_content_variant",
        "StrategistPlan",
        "ContentPackageV2",
        "PlatformVariantRef",
        "PackageStage",
        "QualityState",
        "PublicationState",
        "PackageArtifact",
        "ValueError",
        "TypeError",
        "re",
        "json",
        "pickle",
        "asdict",
        "to_dict",
        "from_dict",
        "serialize",
        "deserialize",
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
        "openai",
        "anthropic",
        "image",
        "video",
        "audio",
        "voiceover",
        "subtitle",
        "thumbnail",
        "media",
        "asset",
        "prompt",
        "messages",
        "template",
        "open",
        "print",
        "exec",
        "eval",
    )

    def test_exactly_one_module_level_function_and_no_classes(self):
        tree = _module_tree()
        functions = [
            n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(
            [f.name for f in functions],
            ["compile_platform_adaptation_instruction"],
        )
        self.assertEqual(
            [n for n in tree.body if isinstance(n, ast.ClassDef)],
            [],
        )

    def test_exact_all(self):
        self.assertEqual(
            compiler_module.__all__,
            ["compile_platform_adaptation_instruction"],
        )

    def test_exactly_one_instruction_construction(self):
        tree = _module_tree()
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "PlatformAdaptationInstruction"
        ]
        self.assertEqual(len(calls), 1)

    def test_imports_exact(self):
        tree = _module_tree()
        imports_from = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
        by_module = {n.module: [a.name for a in n.names] for n in imports_from}
        self.assertEqual(
            by_module,
            {
                "typing": ["Any", "Mapping"],
                "src.domain.platform_adaptation": [
                    "AdaptationSourceContent",
                    "PlatformAdaptationInstruction",
                    "PlatformAdaptationSpec",
                ],
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
        for forbidden in self.FORBIDDEN_IDENTIFIERS:
            self.assertNotIn(forbidden, identifiers)

    def test_source_attribute_access_lock(self):
        tree = _module_tree()
        source_attrs = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        self.assertEqual(
            source_attrs & {"candidate_id", "content_id", "language", "title", "body", "cta", "cta_link"},
            {"candidate_id", "content_id", "language", "title", "body", "cta", "cta_link"},
        )
        self.assertNotIn("metadata", source_attrs)

    def test_spec_attribute_access_lock(self):
        tree = _module_tree()
        spec_attrs = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        self.assertEqual(
            spec_attrs & {"platform", "content_kind", "requires_title", "allows_external_link", "max_characters", "structure", "tone"},
            {"platform", "content_kind", "requires_title", "allows_external_link", "max_characters", "structure", "tone"},
        )

    def test_direct_field_passthrough(self):
        tree = _module_tree()
        function = next(
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        call = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "PlatformAdaptationInstruction"
        )
        keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}

        def _attr_name(node):
            return node.attr if isinstance(node, ast.Attribute) else None

        def _name_id(node):
            return node.id if isinstance(node, ast.Name) else None

        self.assertEqual(_attr_name(keywords["candidate_id"]), "candidate_id")
        self.assertEqual(_attr_name(keywords["source_content_id"]), "content_id")
        self.assertEqual(_attr_name(keywords["platform"]), "platform")
        self.assertEqual(_attr_name(keywords["content_kind"]), "content_kind")
        self.assertEqual(_attr_name(keywords["source_language"]), "language")
        self.assertEqual(_name_id(keywords["output_language"]), "output_language")
        self.assertEqual(_attr_name(keywords["requires_title"]), "requires_title")
        self.assertEqual(_attr_name(keywords["allows_external_link"]), "allows_external_link")
        self.assertEqual(_attr_name(keywords["max_characters"]), "max_characters")
        self.assertEqual(_attr_name(keywords["structure"]), "structure")
        self.assertEqual(_attr_name(keywords["tone"]), "tone")
        self.assertEqual(_attr_name(keywords["source_title"]), "title")
        self.assertEqual(_attr_name(keywords["source_body"]), "body")
        self.assertEqual(_attr_name(keywords["source_cta"]), "cta")
        self.assertEqual(_attr_name(keywords["source_cta_link"]), "cta_link")
        self.assertEqual(_name_id(keywords["metadata"]), "metadata")

    def test_no_conditional_logic(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            self.assertNotIsInstance(
                node, (ast.If, ast.IfExp, ast.Compare, ast.Match)
            )

    def test_no_validation_or_assert(self):
        source = _module_source()
        self.assertNotIn("assert ", source)

    def test_no_try_len_or_slicing(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, (ast.Try, ast.Slice))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"len"})

    def test_no_string_method_calls(self):
        tree = _module_tree()
        function = next(
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        method_calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        ]
        self.assertEqual(method_calls, [])
        # The only Call node in the whole module is the single construction.
        all_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        ]
        self.assertEqual(len(all_calls), 1)


if __name__ == "__main__":
    unittest.main()
