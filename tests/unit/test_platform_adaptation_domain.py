"""Tests for Stage 18A platform adaptation domain contracts."""

import ast
import dataclasses
import unittest
from typing import Any, Mapping, Optional, Tuple

import src.domain.platform_adaptation as platform_adaptation_module
from src.domain.platform_adaptation import (
    AdaptationContentKind,
    AdaptationSourceContent,
    PlatformAdaptationSpec,
    PlatformContentVariant,
)
from src.domain.strategy import TargetPlatform

MODULE_PATH = "src/domain/platform_adaptation.py"

MISSING = dataclasses.MISSING


def _module_source() -> str:
    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _module_tree() -> ast.Module:
    return ast.parse(_module_source(), filename=MODULE_PATH)


class AdaptationContentKindTests(unittest.TestCase):
    def test_enum_members_exact_and_in_declaration_order(self):
        self.assertEqual(
            list(AdaptationContentKind),
            [
                AdaptationContentKind.TEXT_POST,
                AdaptationContentKind.SHORT_VIDEO_SCRIPT,
                AdaptationContentKind.PIN_COPY,
            ],
        )

    def test_enum_values_exact(self):
        self.assertEqual(AdaptationContentKind.TEXT_POST.value, "text_post")
        self.assertEqual(
            AdaptationContentKind.SHORT_VIDEO_SCRIPT.value, "short_video_script"
        )
        self.assertEqual(AdaptationContentKind.PIN_COPY.value, "pin_copy")

    def test_enum_is_string_based(self):
        self.assertTrue(issubclass(AdaptationContentKind, str))
        for member in AdaptationContentKind:
            with self.subTest(member=member):
                self.assertIsInstance(member, str)
                self.assertEqual(str(member), member.value)


class FieldContractTests(unittest.TestCase):
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

    def _assert_contract(self, contract_class, expected_names):
        self.assertTrue(dataclasses.is_dataclass(contract_class))
        self.assertTrue(contract_class.__dataclass_params__.frozen)
        fields = dataclasses.fields(contract_class)
        self.assertEqual([f.name for f in fields], expected_names)
        for field in fields:
            with self.subTest(cls=contract_class.__name__, field=field.name):
                self.assertIs(field.default, MISSING)
                self.assertIs(field.default_factory, MISSING)

    def test_source_content_field_contract(self):
        self._assert_contract(AdaptationSourceContent, self.EXPECTED_SOURCE_FIELDS)

    def test_spec_field_contract(self):
        self._assert_contract(PlatformAdaptationSpec, self.EXPECTED_SPEC_FIELDS)

    def test_variant_field_contract(self):
        self._assert_contract(PlatformContentVariant, self.EXPECTED_VARIANT_FIELDS)


class ConstructionTests(unittest.TestCase):
    def test_real_source_content_construction(self):
        metadata = {"source": "test"}
        source = AdaptationSourceContent(
            content_id="content-123",
            candidate_id="cand-123",
            title="Example AI tool",
            body="Canonical body",
            cta="Try the workflow",
            cta_link="https://example.com/tool",
            language="ru",
            metadata=metadata,
        )
        self.assertEqual(source.content_id, "content-123")
        self.assertEqual(source.candidate_id, "cand-123")
        self.assertEqual(source.title, "Example AI tool")
        self.assertEqual(source.body, "Canonical body")
        self.assertEqual(source.cta, "Try the workflow")
        self.assertEqual(source.cta_link, "https://example.com/tool")
        self.assertEqual(source.language, "ru")
        self.assertIs(source.metadata, metadata)

    def test_real_spec_construction(self):
        structure = ("hook", "body", "cta")
        spec = PlatformAdaptationSpec(
            platform=TargetPlatform.TELEGRAM,
            content_kind=AdaptationContentKind.TEXT_POST,
            max_characters=None,
            requires_title=True,
            allows_external_link=True,
            structure=structure,
            tone="concise",
        )
        self.assertIs(spec.platform, TargetPlatform.TELEGRAM)
        self.assertIs(spec.content_kind, AdaptationContentKind.TEXT_POST)
        self.assertIsNone(spec.max_characters)
        self.assertTrue(spec.requires_title)
        self.assertTrue(spec.allows_external_link)
        self.assertEqual(spec.structure, ("hook", "body", "cta"))
        self.assertIs(spec.structure, structure)
        self.assertEqual(spec.tone, "concise")

    def test_real_variant_construction(self):
        metadata = {"source": "test"}
        variant = PlatformContentVariant(
            variant_id="variant-123",
            candidate_id="cand-123",
            source_content_id="content-123",
            platform=TargetPlatform.X,
            content_kind=AdaptationContentKind.TEXT_POST,
            title="",
            body="Platform-native body",
            cta="Read more",
            cta_link="https://example.com/tool",
            language="ru",
            metadata=metadata,
        )
        self.assertEqual(variant.variant_id, "variant-123")
        self.assertEqual(variant.candidate_id, "cand-123")
        self.assertEqual(variant.source_content_id, "content-123")
        self.assertIs(variant.platform, TargetPlatform.X)
        self.assertIs(variant.content_kind, AdaptationContentKind.TEXT_POST)
        self.assertEqual(variant.title, "")
        self.assertEqual(variant.body, "Platform-native body")
        self.assertEqual(variant.cta, "Read more")
        self.assertEqual(variant.cta_link, "https://example.com/tool")
        self.assertEqual(variant.language, "ru")
        self.assertIs(variant.metadata, metadata)

    def test_empty_strings_are_allowed_by_contract(self):
        source = AdaptationSourceContent(
            content_id="",
            candidate_id="",
            title="",
            body="",
            cta="",
            cta_link="",
            language="",
            metadata={},
        )
        variant = PlatformContentVariant(
            variant_id="",
            candidate_id="",
            source_content_id="",
            platform=TargetPlatform.TELEGRAM,
            content_kind=AdaptationContentKind.TEXT_POST,
            title="",
            body="",
            cta="",
            cta_link="",
            language="",
            metadata={},
        )
        self.assertEqual(source.title, "")
        self.assertEqual(source.body, "")
        self.assertEqual(source.cta, "")
        self.assertEqual(source.cta_link, "")
        self.assertEqual(source.language, "")
        self.assertEqual(variant.title, "")
        self.assertEqual(variant.body, "")
        self.assertEqual(variant.cta, "")
        self.assertEqual(variant.cta_link, "")
        self.assertEqual(variant.language, "")

    def test_max_characters_is_contract_only(self):
        for max_characters in (None, 0, -1, 123456):
            with self.subTest(max_characters=max_characters):
                spec = PlatformAdaptationSpec(
                    platform=TargetPlatform.X,
                    content_kind=AdaptationContentKind.TEXT_POST,
                    max_characters=max_characters,
                    requires_title=False,
                    allows_external_link=False,
                    structure=("body",),
                    tone="neutral",
                )
                self.assertEqual(spec.max_characters, max_characters)

    def test_all_target_platforms_accepted(self):
        self.assertEqual(
            [member.name for member in TargetPlatform],
            [
                "TELEGRAM",
                "X",
                "LINKEDIN",
                "REDDIT",
                "YOUTUBE_SHORTS",
                "TIKTOK",
                "PINTEREST",
            ],
        )
        for platform in TargetPlatform:
            with self.subTest(platform=platform):
                spec = PlatformAdaptationSpec(
                    platform=platform,
                    content_kind=AdaptationContentKind.TEXT_POST,
                    max_characters=None,
                    requires_title=False,
                    allows_external_link=False,
                    structure=("body",),
                    tone="neutral",
                )
                variant = PlatformContentVariant(
                    variant_id=f"variant-{platform.value}",
                    candidate_id="cand-123",
                    source_content_id="content-123",
                    platform=platform,
                    content_kind=AdaptationContentKind.TEXT_POST,
                    title="",
                    body="body",
                    cta="",
                    cta_link="",
                    language="ru",
                    metadata={},
                )
                self.assertIs(spec.platform, platform)
                self.assertIs(variant.platform, platform)

    def test_any_content_kind_can_be_constructed(self):
        representative_platforms = (
            TargetPlatform.TELEGRAM,
            TargetPlatform.X,
            TargetPlatform.YOUTUBE_SHORTS,
            TargetPlatform.PINTEREST,
        )
        for content_kind in AdaptationContentKind:
            for platform in representative_platforms:
                with self.subTest(content_kind=content_kind, platform=platform):
                    spec = PlatformAdaptationSpec(
                        platform=platform,
                        content_kind=content_kind,
                        max_characters=None,
                        requires_title=False,
                        allows_external_link=False,
                        structure=("body",),
                        tone="neutral",
                    )
                    variant = PlatformContentVariant(
                        variant_id="variant-1",
                        candidate_id="cand-123",
                        source_content_id="content-123",
                        platform=platform,
                        content_kind=content_kind,
                        title="",
                        body="body",
                        cta="",
                        cta_link="",
                        language="ru",
                        metadata={},
                    )
                    self.assertIs(spec.content_kind, content_kind)
                    self.assertIs(variant.content_kind, content_kind)


class ImmutabilityTests(unittest.TestCase):
    def test_source_content_frozen(self):
        source = AdaptationSourceContent(
            content_id="content-123",
            candidate_id="cand-123",
            title="t",
            body="b",
            cta="c",
            cta_link="l",
            language="ru",
            metadata={},
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            source.title = "changed"

    def test_spec_frozen(self):
        spec = PlatformAdaptationSpec(
            platform=TargetPlatform.X,
            content_kind=AdaptationContentKind.TEXT_POST,
            max_characters=None,
            requires_title=False,
            allows_external_link=False,
            structure=("body",),
            tone="neutral",
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            spec.max_characters = 280

    def test_variant_frozen(self):
        variant = PlatformContentVariant(
            variant_id="variant-1",
            candidate_id="cand-123",
            source_content_id="content-123",
            platform=TargetPlatform.X,
            content_kind=AdaptationContentKind.TEXT_POST,
            title="",
            body="b",
            cta="",
            cta_link="",
            language="ru",
            metadata={},
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            variant.body = "changed"

    def test_opaque_metadata_identity(self):
        metadata = {
            "nested": {"x": 1},
            "list_like": [1, 2],
            "custom": "value",
        }
        source = AdaptationSourceContent(
            content_id="content-123",
            candidate_id="cand-123",
            title="t",
            body="b",
            cta="c",
            cta_link="l",
            language="ru",
            metadata=metadata,
        )
        variant = PlatformContentVariant(
            variant_id="variant-1",
            candidate_id="cand-123",
            source_content_id="content-123",
            platform=TargetPlatform.X,
            content_kind=AdaptationContentKind.TEXT_POST,
            title="",
            body="b",
            cta="",
            cta_link="",
            language="ru",
            metadata=metadata,
        )
        self.assertIs(source.metadata, metadata)
        self.assertIs(variant.metadata, metadata)
        self.assertEqual(source.metadata, {"nested": {"x": 1}, "list_like": [1, 2], "custom": "value"})


class TypeAnnotationTests(unittest.TestCase):
    def test_source_content_annotations(self):
        annotations = AdaptationSourceContent.__annotations__
        self.assertIs(annotations["content_id"], str)
        self.assertIs(annotations["candidate_id"], str)
        self.assertIs(annotations["title"], str)
        self.assertIs(annotations["body"], str)
        self.assertIs(annotations["cta"], str)
        self.assertIs(annotations["cta_link"], str)
        self.assertIs(annotations["language"], str)
        self.assertEqual(annotations["metadata"], Mapping[str, Any])

    def test_spec_annotations(self):
        annotations = PlatformAdaptationSpec.__annotations__
        self.assertIs(annotations["platform"], TargetPlatform)
        self.assertIs(annotations["content_kind"], AdaptationContentKind)
        self.assertEqual(annotations["max_characters"], Optional[int])
        self.assertIs(annotations["requires_title"], bool)
        self.assertIs(annotations["allows_external_link"], bool)
        self.assertEqual(annotations["structure"], Tuple[str, ...])
        self.assertIs(annotations["tone"], str)

    def test_variant_annotations(self):
        annotations = PlatformContentVariant.__annotations__
        self.assertIs(annotations["variant_id"], str)
        self.assertIs(annotations["candidate_id"], str)
        self.assertIs(annotations["source_content_id"], str)
        self.assertIs(annotations["platform"], TargetPlatform)
        self.assertIs(annotations["content_kind"], AdaptationContentKind)
        self.assertIs(annotations["title"], str)
        self.assertIs(annotations["body"], str)
        self.assertIs(annotations["cta"], str)
        self.assertIs(annotations["cta_link"], str)
        self.assertIs(annotations["language"], str)
        self.assertEqual(annotations["metadata"], Mapping[str, Any])


class StructuralTests(unittest.TestCase):
    MEDIA_FIELD_NAMES = {
        "image",
        "image_url",
        "image_path",
        "video",
        "video_url",
        "video_path",
        "audio",
        "audio_url",
        "audio_path",
        "voiceover",
        "subtitle",
        "thumbnail",
        "media",
        "media_uri",
        "asset",
        "asset_uri",
    }
    FORBIDDEN_IDENTIFIERS = (
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
        "ArtifactKind",
        "ResearchExecutionResult",
        "ExperimentExecutionResult",
        "ResearchRequirement",
        "EvidenceRecord",
        "ExperimentPlan",
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
        "json",
        "pickle",
        "asdict",
        "openai",
        "anthropic",
        "open",
        "print",
        "exec",
        "eval",
    )

    def _collect_identifier_nodes(self, tree):
        identifiers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    identifiers.add(alias.name.split(".")[0])
                    if alias.asname:
                        identifiers.add(alias.asname)
                if isinstance(node, ast.ImportFrom) and node.module:
                    identifiers.add(node.module.split(".")[0])
        return identifiers

    def test_exactly_one_enum_and_three_dataclasses(self):
        tree = _module_tree()
        class_defs = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        self.assertEqual(
            [c.name for c in class_defs],
            [
                "AdaptationContentKind",
                "AdaptationSourceContent",
                "PlatformAdaptationSpec",
                "PlatformContentVariant",
            ],
        )
        enum_classes = [
            c for c in class_defs if any(
                isinstance(base, ast.Name) and base.id == "StrEnum"
                for base in c.bases
            )
        ]
        self.assertEqual([c.name for c in enum_classes], ["AdaptationContentKind"])

    def test_exact_all(self):
        self.assertEqual(
            platform_adaptation_module.__all__,
            [
                "AdaptationContentKind",
                "AdaptationSourceContent",
                "PlatformAdaptationSpec",
                "PlatformContentVariant",
            ],
        )

    def test_zero_functions_anywhere(self):
        tree = _module_tree()
        function_nodes = [
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(function_nodes, [])

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

    def test_module_body_has_only_docstring_imports_all_and_classes(self):
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

    def test_imports_exact(self):
        tree = _module_tree()
        plain_imports = [n for n in tree.body if isinstance(n, ast.Import)]
        self.assertEqual(plain_imports, [])
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

    def test_no_forbidden_identifiers(self):
        identifiers = self._collect_identifier_nodes(_module_tree())
        for forbidden in self.FORBIDDEN_IDENTIFIERS:
            self.assertNotIn(forbidden, identifiers)

    def test_no_platform_mapping_dictionaries_or_limit_constants(self):
        tree = _module_tree()
        for node in tree.body:
            if self._is_all_assignment(node):
                continue
            self.assertNotIsInstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        forbidden_limits = {280, 3000, 5000, 2200}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, int):
                self.assertNotIn(node.value, forbidden_limits)

    def test_no_variant_id_generation_logic(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, (ast.JoinedStr, ast.BinOp, ast.IfExp))

    def test_no_validation_or_serialization_or_post_init(self):
        source = _module_source()
        for token in (
            "__post_init__",
            "validate",
            "ValueError",
            "to_dict",
            "from_dict",
            "serialize",
            "deserialize",
            "asdict",
            "json",
            "pickle",
        ):
            self.assertNotIn(token, source)

    def test_no_defaults_in_dataclass_field_definitions(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            if isinstance(node, (ast.keyword,)) and node.arg in ("default", "default_factory"):
                self.fail(f"dataclass field uses {node.arg}")

    def test_no_media_terms_as_fields(self):
        for contract_class in (
            AdaptationSourceContent,
            PlatformAdaptationSpec,
            PlatformContentVariant,
        ):
            field_names = {f.name for f in dataclasses.fields(contract_class)}
            self.assertEqual(field_names & self.MEDIA_FIELD_NAMES, set())

    def test_no_duplicate_package_state_enums(self):
        tree = _module_tree()
        class_names = {c.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef)}
        for forbidden in (
            "AdaptationStatus",
            "VariantStatus",
            "DraftStatus",
            "QualityState",
            "PublicationState",
            "PackageStage",
        ):
            self.assertNotIn(forbidden, class_names)


if __name__ == "__main__":
    unittest.main()
