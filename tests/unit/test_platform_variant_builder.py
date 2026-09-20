"""Tests for Stage 18C deterministic platform content variant builder.

Updated in 18D-D1: language is a caller-owned, required keyword-only field.
source.language is no longer consumed by the builder.
"""

import ast
import inspect
import unittest

import src.content.platform_variant_builder as builder_module
from src.content.platform_adaptation_policy import get_platform_adaptation_spec
from src.content.platform_variant_builder import build_platform_content_variant
from src.domain.platform_adaptation import (
    AdaptationContentKind,
    AdaptationSourceContent,
    PlatformAdaptationSpec,
    PlatformContentVariant,
)
from src.domain.strategy import TargetPlatform

MODULE_PATH = "src/content/platform_variant_builder.py"


def _module_source() -> str:
    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _module_tree() -> ast.Module:
    return ast.parse(_module_source(), filename=MODULE_PATH)


def _make_source(
    *,
    content_id="content-123",
    candidate_id="cand-123",
    title="Canonical title",
    body="Canonical body",
    cta="Canonical CTA",
    cta_link="https://example.com/tool",
    language="ru",
    metadata=None,
):
    return AdaptationSourceContent(
        content_id=content_id,
        candidate_id=candidate_id,
        title=title,
        body=body,
        cta=cta,
        cta_link=cta_link,
        language=language,
        metadata={"source": "canonical"} if metadata is None else metadata,
    )


def _make_custom_spec(
    *,
    platform=TargetPlatform.X,
    content_kind=AdaptationContentKind.TEXT_POST,
    max_characters=None,
    requires_title=True,
    allows_external_link=True,
    structure=("body",),
    tone="neutral",
):
    return PlatformAdaptationSpec(
        platform=platform,
        content_kind=content_kind,
        max_characters=max_characters,
        requires_title=requires_title,
        allows_external_link=allows_external_link,
        structure=structure,
        tone=tone,
    )


class SignatureTests(unittest.TestCase):
    def test_signature_exact(self):
        signature = inspect.signature(build_platform_content_variant)
        parameters = list(signature.parameters.values())
        self.assertEqual(
            [p.name for p in parameters],
            ["source", "spec", "title", "body", "cta", "language", "metadata"],
        )
        by_name = {p.name: p for p in parameters}
        for name in ("source", "spec"):
            self.assertEqual(
                by_name[name].kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
            )
        for name in ("title", "body", "cta", "language", "metadata"):
            with self.subTest(parameter=name):
                self.assertEqual(by_name[name].kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(by_name[name].default, inspect.Parameter.empty)
        self.assertIs(by_name["language"].annotation, str)


class RealSpecBuildTests(unittest.TestCase):
    """Builds against the real Stage 18B policy specs."""

    def setUp(self):
        self.source = _make_source()

    def test_telegram_build(self):
        metadata = {"adaptation": "telegram"}
        variant = build_platform_content_variant(
            self.source,
            get_platform_adaptation_spec(TargetPlatform.TELEGRAM),
            title="Telegram title",
            body="Telegram body",
            cta="Telegram CTA",
            language="ru",
            metadata=metadata,
        )
        self.assertIsInstance(variant, PlatformContentVariant)
        self.assertEqual(variant.variant_id, "content-123:telegram")
        self.assertEqual(variant.candidate_id, "cand-123")
        self.assertEqual(variant.source_content_id, "content-123")
        self.assertIs(variant.platform, TargetPlatform.TELEGRAM)
        self.assertIs(variant.content_kind, AdaptationContentKind.TEXT_POST)
        self.assertEqual(variant.title, "Telegram title")
        self.assertEqual(variant.body, "Telegram body")
        self.assertEqual(variant.cta, "Telegram CTA")
        self.assertEqual(variant.cta_link, "https://example.com/tool")
        self.assertEqual(variant.language, "ru")
        self.assertIs(variant.metadata, metadata)

    def test_x_title_suppression(self):
        variant = build_platform_content_variant(
            self.source,
            get_platform_adaptation_spec(TargetPlatform.X),
            title="THIS MUST NOT SURVIVE",
            body="X body",
            cta="X CTA",
            language="ru",
            metadata={},
        )
        self.assertEqual(variant.title, "")
        self.assertEqual(variant.body, "X body")
        self.assertEqual(variant.cta, "X CTA")
        self.assertEqual(variant.cta_link, "https://example.com/tool")

    def test_linkedin_title_suppression(self):
        variant = build_platform_content_variant(
            self.source,
            get_platform_adaptation_spec(TargetPlatform.LINKEDIN),
            title="THIS MUST NOT SURVIVE",
            body="LinkedIn body",
            cta="LinkedIn CTA",
            language="ru",
            metadata={},
        )
        self.assertEqual(variant.title, "")
        self.assertEqual(variant.cta_link, "https://example.com/tool")
        self.assertEqual(variant.body, "LinkedIn body")

    def test_reddit_link_suppression(self):
        variant = build_platform_content_variant(
            self.source,
            get_platform_adaptation_spec(TargetPlatform.REDDIT),
            title="Reddit title",
            body="Reddit body",
            cta="Discuss this",
            language="ru",
            metadata={},
        )
        self.assertEqual(variant.title, "Reddit title")
        self.assertEqual(variant.cta, "Discuss this")
        self.assertEqual(variant.cta_link, "")
        self.assertEqual(variant.body, "Reddit body")

    def test_youtube_shorts(self):
        variant = build_platform_content_variant(
            self.source,
            get_platform_adaptation_spec(TargetPlatform.YOUTUBE_SHORTS),
            title="Shorts title",
            body="hook: ...\nsetup: ...\npayoff: ...",
            cta="Follow for more",
            language="ru",
            metadata={},
        )
        self.assertIs(variant.content_kind, AdaptationContentKind.SHORT_VIDEO_SCRIPT)
        self.assertEqual(variant.title, "Shorts title")
        self.assertEqual(variant.cta_link, "")
        self.assertEqual(variant.body, "hook: ...\nsetup: ...\npayoff: ...")

    def test_tiktok(self):
        variant = build_platform_content_variant(
            self.source,
            get_platform_adaptation_spec(TargetPlatform.TIKTOK),
            title="THIS MUST NOT SURVIVE",
            body="TikTok script",
            cta="Link in bio",
            language="ru",
            metadata={},
        )
        self.assertIs(variant.content_kind, AdaptationContentKind.SHORT_VIDEO_SCRIPT)
        self.assertEqual(variant.title, "")
        self.assertEqual(variant.cta_link, "")
        self.assertEqual(variant.body, "TikTok script")
        self.assertEqual(variant.cta, "Link in bio")

    def test_pinterest(self):
        variant = build_platform_content_variant(
            self.source,
            get_platform_adaptation_spec(TargetPlatform.PINTEREST),
            title="Pin title",
            body="Pin description",
            cta="Save this pin",
            language="ru",
            metadata={},
        )
        self.assertIs(variant.content_kind, AdaptationContentKind.PIN_COPY)
        self.assertEqual(variant.title, "Pin title")
        self.assertEqual(variant.cta_link, "https://example.com/tool")


class IdentityAndDeterminismTests(unittest.TestCase):
    def test_deterministic_ids_for_all_platforms(self):
        source = _make_source()
        seen_ids = []
        for platform in TargetPlatform:
            variant = build_platform_content_variant(
                source,
                get_platform_adaptation_spec(platform),
                title="t",
                body="b",
                cta="c",
                language="ru",
                metadata={},
            )
            with self.subTest(platform=platform):
                self.assertEqual(
                    variant.variant_id,
                    f"content-123:{platform.value}",
                )
            seen_ids.append(variant.variant_id)
        self.assertEqual(len(seen_ids), len(set(seen_ids)))

    def test_same_input_equality(self):
        source = _make_source()
        spec = get_platform_adaptation_spec(TargetPlatform.TELEGRAM)
        metadata = {"adaptation": "again"}
        first = build_platform_content_variant(
            source, spec, title="t", body="b", cta="c", language="ru", metadata=metadata
        )
        second = build_platform_content_variant(
            source, spec, title="t", body="b", cta="c", language="ru", metadata=metadata
        )
        self.assertEqual(first, second)
        self.assertIsNot(first, second)

    def test_source_correlation(self):
        source = _make_source(
            content_id="canonical-999",
            candidate_id="candidate-777",
        )
        variant = build_platform_content_variant(
            source,
            get_platform_adaptation_spec(TargetPlatform.X),
            title="t",
            body="b",
            cta="c",
            language="ru",
            metadata={},
        )
        self.assertEqual(variant.variant_id, "canonical-999:x")
        self.assertEqual(variant.candidate_id, "candidate-777")
        self.assertEqual(variant.source_content_id, "canonical-999")


class CallerLanguageOwnershipTests(unittest.TestCase):
    """18D-D1: language is caller-owned; source.language is never consumed."""

    def test_caller_language_uk_overrides_source_ru(self):
        source = _make_source(language="ru")
        variant = build_platform_content_variant(
            source,
            get_platform_adaptation_spec(TargetPlatform.TELEGRAM),
            title="t",
            body="b",
            cta="c",
            language="uk",
            metadata={},
        )
        self.assertEqual(variant.language, "uk")

    def test_caller_empty_language_preserved(self):
        source = _make_source(language="ru")
        variant = build_platform_content_variant(
            source,
            get_platform_adaptation_spec(TargetPlatform.TELEGRAM),
            title="t",
            body="b",
            cta="c",
            language="",
            metadata={},
        )
        self.assertEqual(variant.language, "")

    def test_changing_only_source_language_does_not_change_variant(self):
        spec = get_platform_adaptation_spec(TargetPlatform.TELEGRAM)
        variant_a = build_platform_content_variant(
            _make_source(language="ru"),
            spec,
            title="t",
            body="b",
            cta="c",
            language="uk",
            metadata={},
        )
        variant_b = build_platform_content_variant(
            _make_source(language="en"),
            spec,
            title="t",
            body="b",
            cta="c",
            language="uk",
            metadata={},
        )
        self.assertEqual(variant_a, variant_b)
        self.assertEqual(variant_a.language, "uk")
        self.assertEqual(variant_b.language, "uk")

    def test_source_language_ignored_with_different_sources(self):
        source_a = _make_source(language="ru")
        source_b = _make_source(language="en")
        spec = _make_custom_spec()
        variant_a = build_platform_content_variant(
            source_a, spec, title="t", body="b", cta="c", language="uk", metadata={"m": 1}
        )
        variant_b = build_platform_content_variant(
            source_b, spec, title="t", body="b", cta="c", language="uk", metadata={"m": 1}
        )
        self.assertEqual(variant_a, variant_b)
        self.assertEqual(variant_a.language, "uk")
        self.assertEqual(variant_b.language, "uk")

    def test_language_verbatim(self):
        source = _make_source(language="ru")
        spec = _make_custom_spec()
        for language in ("ru", "uk", "en", "", " xx ", "\nlang\n"):
            with self.subTest(language=language):
                variant = build_platform_content_variant(
                    source, spec, title="t", body="b", cta="c", language=language, metadata={}
                )
                self.assertEqual(variant.language, language)


class CustomSpecPolicyTests(unittest.TestCase):
    def test_title_policy_true(self):
        source = _make_source()
        spec = _make_custom_spec(requires_title=True)
        variant = build_platform_content_variant(
            source, spec, title="Custom title", body="b", cta="c", language="ru", metadata={}
        )
        self.assertEqual(variant.title, "Custom title")

    def test_title_policy_false(self):
        source = _make_source()
        spec = _make_custom_spec(requires_title=False)
        variant = build_platform_content_variant(
            source, spec, title="ignored", body="b", cta="c", language="ru", metadata={}
        )
        self.assertEqual(variant.title, "")

    def test_link_policy_true_no_url_validation(self):
        source = _make_source(cta_link="not-a-url")
        spec = _make_custom_spec(allows_external_link=True)
        variant = build_platform_content_variant(
            source, spec, title="t", body="b", cta="c", language="ru", metadata={}
        )
        self.assertEqual(variant.cta_link, "not-a-url")

    def test_link_policy_false(self):
        source = _make_source(cta_link="not-a-url")
        spec = _make_custom_spec(allows_external_link=False)
        variant = build_platform_content_variant(
            source, spec, title="t", body="b", cta="c", language="ru", metadata={}
        )
        self.assertEqual(variant.cta_link, "")

    def test_cta_text_independent_from_link_policy(self):
        source = _make_source()
        spec = _make_custom_spec(allows_external_link=False)
        variant = build_platform_content_variant(
            source, spec, title="t", body="b", cta="Discuss this", language="ru", metadata={}
        )
        self.assertEqual(variant.cta, "Discuss this")
        self.assertEqual(variant.cta_link, "")


class NoFallbackTests(unittest.TestCase):
    def test_body_never_falls_back(self):
        source = _make_source(body="CANONICAL")
        spec = _make_custom_spec()
        empty = build_platform_content_variant(
            source, spec, title="t", body="", cta="c", language="ru", metadata={}
        )
        self.assertEqual(empty.body, "")
        adapted = build_platform_content_variant(
            source, spec, title="t", body="ADAPTED", cta="c", language="ru", metadata={}
        )
        self.assertEqual(adapted.body, "ADAPTED")

    def test_title_never_falls_back(self):
        source = _make_source(title="CANONICAL TITLE")
        spec = _make_custom_spec(requires_title=True)
        variant = build_platform_content_variant(
            source, spec, title="", body="b", cta="c", language="ru", metadata={}
        )
        self.assertEqual(variant.title, "")

    def test_cta_never_falls_back(self):
        source = _make_source(cta="CANONICAL CTA")
        spec = _make_custom_spec()
        variant = build_platform_content_variant(
            source, spec, title="t", body="b", cta="", language="ru", metadata={}
        )
        self.assertEqual(variant.cta, "")

    def test_language_never_falls_back(self):
        source = _make_source(language="CANONICAL-LANG")
        spec = _make_custom_spec()
        variant = build_platform_content_variant(
            source, spec, title="t", body="b", cta="c", language="", metadata={}
        )
        self.assertEqual(variant.language, "")

    def test_source_text_fields_not_used(self):
        base = _make_source(
            title="Title A",
            body="Body A",
            cta="CTA A",
            language="ru",
            metadata={"source": "a"},
        )
        other = _make_source(
            title="Title B",
            body="Body B",
            cta="CTA B",
            language="en",
            metadata={"source": "b"},
        )
        spec = _make_custom_spec()
        metadata = {"adaptation": "fixed"}
        first = build_platform_content_variant(
            base, spec, title="fixed title", body="fixed body", cta="fixed cta", language="uk", metadata=metadata
        )
        second = build_platform_content_variant(
            other, spec, title="fixed title", body="fixed body", cta="fixed cta", language="uk", metadata=metadata
        )
        self.assertEqual(first, second)
        self.assertEqual(first.language, "uk")
        self.assertEqual(first.metadata, {"adaptation": "fixed"})

    def test_source_link_does_affect_allowed_link(self):
        source_a = _make_source(cta_link="A")
        source_b = _make_source(cta_link="B")
        spec = _make_custom_spec(allows_external_link=True)
        variant_a = build_platform_content_variant(
            source_a, spec, title="t", body="b", cta="c", language="ru", metadata={}
        )
        variant_b = build_platform_content_variant(
            source_b, spec, title="t", body="b", cta="c", language="ru", metadata={}
        )
        self.assertEqual(variant_a.cta_link, "A")
        self.assertEqual(variant_b.cta_link, "B")

    def test_source_link_does_not_affect_suppressed_link(self):
        source_a = _make_source(cta_link="A")
        source_b = _make_source(cta_link="B")
        spec = _make_custom_spec(allows_external_link=False)
        variant_a = build_platform_content_variant(
            source_a, spec, title="t", body="b", cta="c", language="ru", metadata={}
        )
        variant_b = build_platform_content_variant(
            source_b, spec, title="t", body="b", cta="c", language="ru", metadata={}
        )
        self.assertEqual(variant_a.cta_link, "")
        self.assertEqual(variant_b.cta_link, "")


class MetadataTests(unittest.TestCase):
    def test_caller_metadata_identity(self):
        metadata = {
            "nested": {"x": 1},
            "items": [1, 2],
        }
        source = _make_source()
        variant = build_platform_content_variant(
            source, _make_custom_spec(), title="t", body="b", cta="c", language="ru", metadata=metadata
        )
        self.assertIs(variant.metadata, metadata)

    def test_source_metadata_not_merged(self):
        source = _make_source(
            metadata={"source_only": True, "collision": "source"},
        )
        variant_metadata = {
            "variant_only": True,
            "collision": "variant",
        }
        variant = build_platform_content_variant(
            source, _make_custom_spec(), title="t", body="b", cta="c", language="ru", metadata=variant_metadata
        )
        self.assertIs(variant.metadata, variant_metadata)
        self.assertEqual(
            variant.metadata,
            {"variant_only": True, "collision": "variant"},
        )
        self.assertNotIn("source_only", variant.metadata)


class SpecFieldIndifferenceTests(unittest.TestCase):
    def test_spec_max_characters_ignored(self):
        source = _make_source()
        long_body = "x" * 10_000
        variants = []
        for max_characters in (1, 999_999, None):
            spec = _make_custom_spec(max_characters=max_characters)
            variants.append(
                build_platform_content_variant(
                    source, spec, title="t", body=long_body, cta="c", language="ru", metadata={}
                )
            )
        for variant in variants:
            self.assertEqual(variant.body, long_body)
        self.assertEqual(variants[0], variants[1])
        self.assertEqual(variants[1], variants[2])

    def test_spec_structure_tone_do_not_affect_build(self):
        source = _make_source()
        spec_a = _make_custom_spec(
            max_characters=None,
            structure=("hook", "cta"),
            tone="tone-a",
        )
        spec_b = _make_custom_spec(
            max_characters=1234,
            structure=("single",),
            tone="tone-b",
        )
        variant_a = build_platform_content_variant(
            source, spec_a, title="t", body="b", cta="c", language="ru", metadata={}
        )
        variant_b = build_platform_content_variant(
            source, spec_b, title="t", body="b", cta="c", language="ru", metadata={}
        )
        self.assertEqual(variant_a, variant_b)

    def test_content_kind_passthrough(self):
        source = _make_source()
        for content_kind in AdaptationContentKind:
            with self.subTest(content_kind=content_kind):
                spec = _make_custom_spec(content_kind=content_kind)
                variant = build_platform_content_variant(
                    source, spec, title="t", body="b", cta="c", language="ru", metadata={}
                )
                self.assertIs(variant.content_kind, content_kind)


class EdgeCaseTests(unittest.TestCase):
    def test_empty_values_accepted(self):
        source = _make_source(
            content_id="",
            candidate_id="",
            cta_link="",
            language="",
        )
        variant = build_platform_content_variant(
            source,
            get_platform_adaptation_spec(TargetPlatform.TELEGRAM),
            title="",
            body="",
            cta="",
            language="",
            metadata={},
        )
        self.assertEqual(variant.variant_id, ":telegram")
        self.assertEqual(variant.candidate_id, "")
        self.assertEqual(variant.source_content_id, "")
        self.assertEqual(variant.title, "")
        self.assertEqual(variant.body, "")
        self.assertEqual(variant.cta, "")
        self.assertEqual(variant.cta_link, "")
        self.assertEqual(variant.language, "")

    def test_input_immutability(self):
        metadata = {"adaptation": "x"}
        source = _make_source(metadata=metadata)
        spec = get_platform_adaptation_spec(TargetPlatform.TELEGRAM)
        source_ref = source
        source_metadata_ref = source.metadata
        spec_structure_ref = spec.structure
        variant = build_platform_content_variant(
            source, spec, title="t", body="b", cta="c", language="ru", metadata=metadata
        )
        self.assertIs(source, source_ref)
        self.assertIs(source.metadata, source_metadata_ref)
        self.assertIs(spec.structure, spec_structure_ref)
        self.assertEqual(
            source,
            _make_source(metadata=metadata),
        )
        self.assertEqual(variant.title, "t")


class StructuralTests(unittest.TestCase):
    FORBIDDEN_IDENTIFIERS = (
        "get_platform_adaptation_spec",
        "get_platform_adaptation_specs",
        "TargetPlatform",
        "AdaptationContentKind",
        "PlatformAdaptationExecutionResult",
        "AdaptationExecutionStatus",
        "StrategistPlan",
        "ContentPackageV2",
        "PlatformVariantRef",
        "PackageStage",
        "QualityState",
        "PublicationState",
        "PackageArtifact",
        "ValueError",
        "TypeError",
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
        "re",
        "json",
        "pickle",
        "asdict",
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
        "open",
        "print",
        "exec",
        "eval",
    )

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

    def _collect_identifier_nodes(self, tree) -> set:
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

    def test_exactly_one_module_level_function_and_no_classes(self):
        tree = _module_tree()
        functions = [
            n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(
            [f.name for f in functions],
            ["build_platform_content_variant"],
        )
        self.assertEqual(
            [n for n in tree.body if isinstance(n, ast.ClassDef)],
            [],
        )

    def test_exact_all(self):
        self.assertEqual(
            builder_module.__all__,
            ["build_platform_content_variant"],
        )

    def test_exactly_one_variant_construction(self):
        tree = _module_tree()
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "PlatformContentVariant"
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
                    "PlatformAdaptationSpec",
                    "PlatformContentVariant",
                ],
            },
        )
        self.assertEqual(
            [n for n in tree.body if isinstance(n, ast.Import)],
            [],
        )

    def test_no_forbidden_identifiers(self):
        identifiers = self._collect_identifier_nodes(_module_tree())
        for forbidden in self.FORBIDDEN_IDENTIFIERS:
            self.assertNotIn(forbidden, identifiers)

    def test_no_try_assert_len_or_slicing(self):
        tree = _module_tree()
        source = _module_source()
        self.assertNotIn("assert ", source)
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, (ast.Try, ast.Slice))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"len"})

    def test_source_accesses_exactly_limited(self):
        tree = _module_tree()
        source_attrs = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        self.assertEqual(
            source_attrs & {"content_id", "candidate_id", "cta_link"},
            {"content_id", "candidate_id", "cta_link"},
        )
        for forbidden in ("title", "body", "cta", "metadata", "language"):
            self.assertNotIn(forbidden, source_attrs)

    def test_no_source_language_attribute_access(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(node.attr, "language")

    def test_spec_accesses_exactly_limited(self):
        tree = _module_tree()
        spec_attrs = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        self.assertEqual(
            spec_attrs & {"platform", "content_kind", "requires_title", "allows_external_link"},
            {"platform", "content_kind", "requires_title", "allows_external_link"},
        )
        for forbidden in ("max_characters", "structure", "tone"):
            self.assertNotIn(forbidden, spec_attrs)

    def test_variant_id_expression_structure(self):
        tree = _module_tree()
        function = next(
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        joined = [
            n
            for n in ast.walk(function)
            if isinstance(n, ast.JoinedStr)
        ]
        self.assertEqual(len(joined), 1)
        formatted_values = [
            n.value
            for n in joined[0].values
            if isinstance(n, ast.FormattedValue)
        ]
        self.assertEqual(len(formatted_values), 2)
        constants = [
            n.value
            for n in joined[0].values
            if isinstance(n, ast.Constant)
        ]
        self.assertEqual(constants, [":"])

    def test_title_expression_uses_only_requires_title(self):
        tree = _module_tree()
        function = next(
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        title_keywords = [
            kw.value
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "PlatformContentVariant"
            for kw in node.keywords
            if kw.arg == "title"
        ]
        self.assertEqual(len(title_keywords), 1)
        expr = title_keywords[0]
        self.assertIsInstance(expr, ast.IfExp)
        condition = expr.test
        self.assertIsInstance(condition, ast.Attribute)
        self.assertEqual(condition.attr, "requires_title")
        self.assertIsInstance(condition.value, ast.Name)
        self.assertEqual(condition.value.id, "spec")
        self.assertIsInstance(expr.body, ast.Name)
        self.assertEqual(expr.body.id, "title")

    def test_link_expression_uses_only_allows_external_link(self):
        tree = _module_tree()
        function = next(
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        link_keywords = [
            kw.value
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "PlatformContentVariant"
            for kw in node.keywords
            if kw.arg == "cta_link"
        ]
        self.assertEqual(len(link_keywords), 1)
        expr = link_keywords[0]
        self.assertIsInstance(expr, ast.IfExp)
        condition = expr.test
        self.assertIsInstance(condition, ast.Attribute)
        self.assertEqual(condition.attr, "allows_external_link")
        self.assertIsInstance(expr.body, ast.Attribute)
        self.assertEqual(expr.body.attr, "cta_link")
        self.assertIsInstance(expr.orelse, ast.Constant)
        self.assertEqual(expr.orelse.value, "")

    def test_exactly_two_conditional_expressions(self):
        tree = _module_tree()
        if_exps = [n for n in ast.walk(tree) if isinstance(n, ast.IfExp)]
        self.assertEqual(len(if_exps), 2)

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
            and node.func.id == "PlatformContentVariant"
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
        self.assertEqual(_name_id(keywords["body"]), "body")
        self.assertEqual(_name_id(keywords["cta"]), "cta")
        self.assertEqual(_name_id(keywords["language"]), "language")
        self.assertEqual(_name_id(keywords["metadata"]), "metadata")

    def test_language_has_no_default(self):
        signature = inspect.signature(build_platform_content_variant)
        language = signature.parameters["language"]
        self.assertEqual(language.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(language.default, inspect.Parameter.empty)

    def test_no_if_statements_or_platform_comparisons(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, ast.If)
            if isinstance(node, ast.Compare):
                self.fail("comparison present in production module")

    def test_no_transformation_helper_identifiers(self):
        tree = _module_tree()
        code_parts = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                code_parts.append(ast.unparse(node))
        code = "\n".join(code_parts) if code_parts else ""
        for token in (
            "adapt_",
            "rewrite",
            "truncate",
            "shorten",
            "summarize",
            "translate",
            "normalize",
            "render",
            "generate",
        ):
            self.assertNotIn(token, code)


if __name__ == "__main__":
    unittest.main()
