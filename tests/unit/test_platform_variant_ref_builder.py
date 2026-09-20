"""Tests for Stage 18E-A platform variant package-reference builder."""

import ast
import inspect
import unittest

import src.content.platform_variant_ref_builder as ref_builder_module
from src.content.platform_variant_ref_builder import build_platform_variant_ref
from src.domain.content_package import (
    PlatformVariantRef,
    PublicationState,
    QualityState,
)
from src.domain.platform_adaptation import (
    AdaptationContentKind,
    PlatformContentVariant,
)
from src.domain.strategy import TargetPlatform

MODULE_PATH = "src/content/platform_variant_ref_builder.py"


def _module_source() -> str:
    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _module_tree() -> ast.Module:
    return ast.parse(_module_source(), filename=MODULE_PATH)


def _make_variant(**overrides):
    values = dict(
        variant_id="content-123:telegram",
        candidate_id="cand-123",
        source_content_id="content-123",
        platform=TargetPlatform.TELEGRAM,
        content_kind=AdaptationContentKind.TEXT_POST,
        title="Adapted title",
        body="Adapted body",
        cta="Adapted CTA",
        cta_link="https://example.com",
        language="uk",
        metadata={"execution": "test"},
    )
    values.update(overrides)
    return PlatformContentVariant(**values)


class RepresentativeBuildTests(unittest.TestCase):
    def test_representative_build(self):
        variant = _make_variant()
        ref = build_platform_variant_ref(
            variant,
            content_ref="variant://content-123:telegram",
        )
        self.assertIsInstance(ref, PlatformVariantRef)
        self.assertEqual(ref.variant_id, "content-123:telegram")
        self.assertIs(ref.platform, TargetPlatform.TELEGRAM)
        self.assertEqual(ref.content_ref, "variant://content-123:telegram")
        self.assertIs(ref.quality_state, QualityState.NOT_CHECKED)
        self.assertIs(ref.publication_state, PublicationState.NOT_READY)

    def test_all_platforms(self):
        for platform in TargetPlatform:
            with self.subTest(platform=platform):
                variant = _make_variant(
                    variant_id=f"content-123:{platform.value}",
                    platform=platform,
                )
                ref = build_platform_variant_ref(variant, content_ref="ref")
                self.assertIs(ref.platform, platform)

    def test_variant_id_passthrough(self):
        for variant_id in ("", "variant", " content:id ", "\nvariant\n"):
            with self.subTest(variant_id=variant_id):
                ref = build_platform_variant_ref(
                    _make_variant(variant_id=variant_id), content_ref="ref"
                )
                self.assertEqual(ref.variant_id, variant_id)

    def test_content_ref_passthrough(self):
        for content_ref in (
            "",
            "ref",
            "variant://content-123:telegram",
            "/tmp/test",
            "https://example.invalid/x",
            " opaque ref ",
            "\nref\n",
        ):
            with self.subTest(content_ref=content_ref):
                ref = build_platform_variant_ref(
                    _make_variant(), content_ref=content_ref
                )
                self.assertEqual(ref.content_ref, content_ref)

    def test_content_ref_independent_of_variant_id(self):
        ref = build_platform_variant_ref(
            _make_variant(variant_id="variant-A"),
            content_ref="storage-B",
        )
        self.assertEqual(ref.variant_id, "variant-A")
        self.assertEqual(ref.content_ref, "storage-B")

    def test_initial_states_fixed(self):
        variants = [
            _make_variant(),
            _make_variant(variant_id="other:id", platform=TargetPlatform.X),
        ]
        content_refs = ["variant://a", "", "memory://abc"]
        for variant in variants:
            for content_ref in content_refs:
                with self.subTest(variant_id=variant.variant_id, content_ref=content_ref):
                    ref = build_platform_variant_ref(variant, content_ref=content_ref)
                    self.assertIs(ref.quality_state, QualityState.NOT_CHECKED)
                    self.assertIs(ref.publication_state, PublicationState.NOT_READY)


class IndifferenceAndDeterminismTests(unittest.TestCase):
    def test_variant_content_does_not_affect_ref(self):
        base = _make_variant()
        other = _make_variant(
            candidate_id="other-candidate",
            source_content_id="other-content",
            content_kind=AdaptationContentKind.PIN_COPY,
            title="Other title",
            body="Other body",
            cta="Other CTA",
            cta_link="https://other.example",
            language="en",
            metadata={"other": True},
        )
        ref_base = build_platform_variant_ref(base, content_ref="same-ref")
        ref_other = build_platform_variant_ref(other, content_ref="same-ref")
        self.assertEqual(ref_base, ref_other)

    def test_metadata_not_propagated(self):
        variant = _make_variant(
            metadata={"nested": {"deep": [1, 2]}, "opaque": "value"},
        )
        ref = build_platform_variant_ref(variant, content_ref="ref")
        self.assertEqual(
            ref._fields
            if hasattr(ref, "_fields")
            else [f.name for f in __import__("dataclasses").fields(ref)],
            ["variant_id", "platform", "content_ref", "quality_state", "publication_state"],
        )

    def test_immutability(self):
        variant = _make_variant()
        snapshot = variant
        build_platform_variant_ref(variant, content_ref="ref")
        self.assertIs(variant, snapshot)
        self.assertEqual(variant, _make_variant())

    def test_same_input_determinism(self):
        variant = _make_variant()
        first = build_platform_variant_ref(variant, content_ref="ref")
        second = build_platform_variant_ref(variant, content_ref="ref")
        self.assertEqual(first, second)
        self.assertIsNot(first, second)


class SignatureTests(unittest.TestCase):
    def test_signature_exact(self):
        signature = inspect.signature(build_platform_variant_ref)
        parameters = list(signature.parameters.values())
        self.assertEqual(
            [p.name for p in parameters],
            ["variant", "content_ref"],
        )
        variant_param = parameters[0]
        content_ref_param = parameters[1]
        self.assertEqual(variant_param.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        self.assertEqual(content_ref_param.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(content_ref_param.annotation, str)
        self.assertIs(content_ref_param.default, inspect.Parameter.empty)
        self.assertIs(signature.return_annotation, PlatformVariantRef)

    def test_no_caller_state_input(self):
        signature = inspect.signature(build_platform_variant_ref)
        self.assertNotIn("quality_state", signature.parameters)
        self.assertNotIn("publication_state", signature.parameters)
        self.assertNotIn("status", signature.parameters)


class StructuralTests(unittest.TestCase):
    FORBIDDEN_IDENTIFIERS = (
        "ContentPackageV2",
        "PackageStage",
        "PackageArtifact",
        "AnalyticsLink",
        "attach_platform_variant",
        "transition_package_stage",
        "TargetPlatform",
        "AdaptationContentKind",
        "PlatformAdaptationExecutionResult",
        "PlatformAdaptationInstruction",
        "AdaptationExecutionStatus",
        "candidate_id",
        "source_content_id",
        "content_kind",
        "title",
        "body",
        "cta",
        "cta_link",
        "language",
        "metadata",
        "strip",
        "lower",
        "upper",
        "normalize",
        "urlparse",
        "to_dict",
        "from_dict",
        "serialize",
        "deserialize",
        "json",
        "pickle",
        "asdict",
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
        "prompt",
        "model",
        "provider",
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
            ["build_platform_variant_ref"],
        )
        self.assertEqual(
            [n for n in tree.body if isinstance(n, ast.ClassDef)],
            [],
        )

    def test_exact_all(self):
        self.assertEqual(
            ref_builder_module.__all__,
            ["build_platform_variant_ref"],
        )

    def test_imports_exact(self):
        tree = _module_tree()
        imports_from = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
        by_module = {n.module: [a.name for a in n.names] for n in imports_from}
        self.assertEqual(
            by_module,
            {
                "src.domain.content_package": [
                    "PlatformVariantRef",
                    "PublicationState",
                    "QualityState",
                ],
                "src.domain.platform_adaptation": ["PlatformContentVariant"],
            },
        )
        self.assertEqual(
            [n for n in tree.body if isinstance(n, ast.Import)],
            [],
        )

    def test_exactly_one_ref_construction_and_zero_other_calls(self):
        tree = _module_tree()
        all_calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
        ]
        self.assertEqual(len(all_calls), 1)
        self.assertIsInstance(all_calls[0].func, ast.Name)
        self.assertEqual(all_calls[0].func.id, "PlatformVariantRef")

    def test_no_control_flow_or_validation(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            self.assertNotIsInstance(
                node, (ast.If, ast.IfExp, ast.Compare, ast.Raise, ast.Try)
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

    def test_variant_attribute_access_lock(self):
        tree = _module_tree()
        attribute_names = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        self.assertEqual(
            attribute_names & {"variant_id", "platform"},
            {"variant_id", "platform"},
        )

    def test_direct_construction_lock(self):
        tree = _module_tree()
        call = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "PlatformVariantRef"
        )
        self.assertEqual(len(call.args), 0)
        keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
        self.assertEqual(
            set(keywords),
            {"variant_id", "platform", "content_ref", "quality_state", "publication_state"},
        )

        def _attr_chain(node):
            parts = []
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                parts.append(node.id)
            return ".".join(reversed(parts))

        self.assertEqual(_attr_chain(keywords["variant_id"]), "variant.variant_id")
        self.assertEqual(_attr_chain(keywords["platform"]), "variant.platform")
        self.assertEqual(keywords["content_ref"].id, "content_ref")
        self.assertEqual(
            _attr_chain(keywords["quality_state"]),
            "QualityState.NOT_CHECKED",
        )
        self.assertEqual(
            _attr_chain(keywords["publication_state"]),
            "PublicationState.NOT_READY",
        )

    def test_state_member_lock(self):
        tree = _module_tree()
        attribute_names = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        quality_members = attribute_names & {
            "NOT_CHECKED",
            "PENDING",
            "APPROVED",
            "REJECTED",
            "MANUAL_REVIEW",
        }
        publication_members = attribute_names & {
            "NOT_READY",
            "READY",
            "PUBLISHING",
            "PARTIALLY_PUBLISHED",
            "PUBLISHED",
            "FAILED",
            "MANUAL_REVIEW",
        }
        self.assertEqual(quality_members, {"NOT_CHECKED"})
        self.assertEqual(publication_members, {"NOT_READY"})


if __name__ == "__main__":
    unittest.main()
