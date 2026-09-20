"""Tests for Stage 18D-D2 execution-result to platform-variant boundary."""

import ast
import inspect
import unittest

import src.content.platform_adaptation_result_boundary as boundary_module
from src.content.platform_adaptation_result_boundary import (
    build_platform_variant_from_execution_result,
)
from src.domain.platform_adaptation import (
    AdaptationContentKind,
    AdaptationSourceContent,
    PlatformAdaptationSpec,
    PlatformContentVariant,
)
from src.domain.platform_adaptation_execution import (
    AdaptationExecutionStatus,
    PlatformAdaptationExecutionResult,
)
from src.domain.strategy import TargetPlatform

MODULE_PATH = "src/content/platform_adaptation_result_boundary.py"


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
        cta_link="https://example.com",
        language="ru",
        metadata={"source": "canonical"},
    )
    values.update(overrides)
    return AdaptationSourceContent(**values)


def _make_spec(**overrides):
    values = dict(
        platform=TargetPlatform.TELEGRAM,
        content_kind=AdaptationContentKind.TEXT_POST,
        max_characters=None,
        requires_title=True,
        allows_external_link=True,
        structure=("hook", "context", "value", "cta"),
        tone="concise and practical",
    )
    values.update(overrides)
    return PlatformAdaptationSpec(**values)


def _make_result(**overrides):
    values = dict(
        candidate_id="cand-123",
        source_content_id="content-123",
        platform=TargetPlatform.TELEGRAM,
        content_kind=AdaptationContentKind.TEXT_POST,
        title="Adapted title",
        body="Adapted body",
        cta="Adapted CTA",
        output_language="uk",
        status=AdaptationExecutionStatus.COMPLETED,
        metadata={"execution": "test"},
    )
    values.update(overrides)
    return PlatformAdaptationExecutionResult(**values)


class HappyPathTests(unittest.TestCase):
    def test_happy_path(self):
        source = _make_source()
        spec = _make_spec()
        result = _make_result()
        variant = build_platform_variant_from_execution_result(source, spec, result)
        self.assertIsInstance(variant, PlatformContentVariant)
        self.assertEqual(variant.variant_id, "content-123:telegram")
        self.assertEqual(variant.candidate_id, "cand-123")
        self.assertEqual(variant.source_content_id, "content-123")
        self.assertIs(variant.platform, TargetPlatform.TELEGRAM)
        self.assertIs(variant.content_kind, AdaptationContentKind.TEXT_POST)
        self.assertEqual(variant.title, "Adapted title")
        self.assertEqual(variant.body, "Adapted body")
        self.assertEqual(variant.cta, "Adapted CTA")
        self.assertEqual(variant.cta_link, "https://example.com")
        self.assertEqual(variant.language, "uk")
        self.assertIs(variant.metadata, result.metadata)

    def test_output_language_ownership(self):
        source = _make_source(language="ru")
        spec = _make_spec()
        english = build_platform_variant_from_execution_result(
            source, spec, _make_result(output_language="en")
        )
        self.assertEqual(english.language, "en")
        empty = build_platform_variant_from_execution_result(
            source, spec, _make_result(output_language="")
        )
        self.assertEqual(empty.language, "")
        self.assertNotEqual(english.language, source.language)

    def test_title_policy_still_owned_by_18c(self):
        source = _make_source()
        spec = _make_spec(
            platform=TargetPlatform.X,
            requires_title=False,
        )
        result = _make_result(
            platform=TargetPlatform.X,
            title="THIS MUST NOT SURVIVE",
        )
        variant = build_platform_variant_from_execution_result(source, spec, result)
        self.assertEqual(variant.title, "")

    def test_link_policy_still_owned_by_18c(self):
        source = _make_source(cta_link="https://example.com")
        spec = _make_spec(platform=TargetPlatform.REDDIT, allows_external_link=False)
        result = _make_result(platform=TargetPlatform.REDDIT)
        variant = build_platform_variant_from_execution_result(source, spec, result)
        self.assertEqual(variant.cta_link, "")

    def test_source_link_survives_when_allowed(self):
        source = _make_source(cta_link="not-a-url")
        spec = _make_spec(allows_external_link=True)
        variant = build_platform_variant_from_execution_result(
            source, spec, _make_result()
        )
        self.assertEqual(variant.cta_link, "not-a-url")

    def test_completed_empty_output_allowed(self):
        variant = build_platform_variant_from_execution_result(
            _make_source(),
            _make_spec(),
            _make_result(title="", body="", cta="", output_language=""),
        )
        self.assertEqual(variant.title, "")
        self.assertEqual(variant.body, "")
        self.assertEqual(variant.cta, "")
        self.assertEqual(variant.language, "")

    def test_metadata_identity(self):
        metadata = {
            "nested": {"x": 1},
            "items": [1, 2],
        }
        variant = build_platform_variant_from_execution_result(
            _make_source(), _make_spec(), _make_result(metadata=metadata)
        )
        self.assertIs(variant.metadata, metadata)

    def test_source_metadata_ignored(self):
        source = _make_source(
            metadata={"source_only": True, "collision": "source"},
        )
        result_metadata = {
            "result_only": True,
            "collision": "result",
        }
        variant = build_platform_variant_from_execution_result(
            source, _make_spec(), _make_result(metadata=result_metadata)
        )
        self.assertIs(variant.metadata, result_metadata)
        self.assertEqual(
            variant.metadata,
            {"result_only": True, "collision": "result"},
        )
        self.assertNotIn("source_only", variant.metadata)

    def test_custom_spec_accepted(self):
        source = _make_source()
        spec = _make_spec(
            content_kind=AdaptationContentKind.PIN_COPY,
            requires_title=False,
            allows_external_link=False,
            max_characters=-99,
            structure=("custom",),
            tone="custom",
        )
        result = _make_result(content_kind=AdaptationContentKind.PIN_COPY)
        variant = build_platform_variant_from_execution_result(source, spec, result)
        self.assertIs(variant.platform, TargetPlatform.TELEGRAM)
        self.assertIs(variant.content_kind, AdaptationContentKind.PIN_COPY)
        self.assertEqual(variant.cta_link, "")
        self.assertEqual(variant.title, "")

    def test_long_body_not_enforced(self):
        long_body = "x" * 10_000
        spec = _make_spec(max_characters=1)
        variant = build_platform_variant_from_execution_result(
            _make_source(), spec, _make_result(body=long_body)
        )
        self.assertEqual(variant.body, long_body)

    def test_same_input_determinism(self):
        source = _make_source()
        spec = _make_spec()
        result = _make_result()
        first = build_platform_variant_from_execution_result(source, spec, result)
        second = build_platform_variant_from_execution_result(source, spec, result)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)


class ValidationTests(unittest.TestCase):
    def test_candidate_mismatch(self):
        with self.assertRaises(ValueError) as ctx:
            build_platform_variant_from_execution_result(
                _make_source(),
                _make_spec(),
                _make_result(candidate_id="other"),
            )
        self.assertEqual(str(ctx.exception), "candidate_id mismatch")

    def test_source_content_mismatch(self):
        with self.assertRaises(ValueError) as ctx:
            build_platform_variant_from_execution_result(
                _make_source(),
                _make_spec(),
                _make_result(source_content_id="other-content"),
            )
        self.assertEqual(str(ctx.exception), "source_content_id mismatch")

    def test_platform_mismatch(self):
        with self.assertRaises(ValueError) as ctx:
            build_platform_variant_from_execution_result(
                _make_source(),
                _make_spec(),
                _make_result(platform=TargetPlatform.X),
            )
        self.assertEqual(str(ctx.exception), "platform mismatch")

    def test_content_kind_mismatch(self):
        with self.assertRaises(ValueError) as ctx:
            build_platform_variant_from_execution_result(
                _make_source(),
                _make_spec(),
                _make_result(content_kind=AdaptationContentKind.PIN_COPY),
            )
        self.assertEqual(str(ctx.exception), "content_kind mismatch")

    def test_failed_status(self):
        with self.assertRaises(ValueError) as ctx:
            build_platform_variant_from_execution_result(
                _make_source(),
                _make_spec(),
                _make_result(status=AdaptationExecutionStatus.FAILED),
            )
        self.assertEqual(str(ctx.exception), "execution result is not completed")

    def test_manual_review_status(self):
        with self.assertRaises(ValueError) as ctx:
            build_platform_variant_from_execution_result(
                _make_source(),
                _make_spec(),
                _make_result(status=AdaptationExecutionStatus.MANUAL_REVIEW),
            )
        self.assertEqual(str(ctx.exception), "execution result is not completed")

    def test_validation_order(self):
        cases = [
            (
                "candidate_id mismatch",
                dict(candidate_id="other"),
            ),
            (
                "source_content_id mismatch",
                dict(source_content_id="other-content"),
            ),
            (
                "platform mismatch",
                dict(platform=TargetPlatform.X),
            ),
            (
                "content_kind mismatch",
                dict(content_kind=AdaptationContentKind.PIN_COPY),
            ),
            (
                "execution result is not completed",
                dict(status=AdaptationExecutionStatus.FAILED),
            ),
        ]
        for expected_message, overrides in cases:
            with self.subTest(expected=expected_message):
                with self.assertRaises(ValueError) as ctx:
                    build_platform_variant_from_execution_result(
                        _make_source(),
                        _make_spec(),
                        _make_result(**overrides),
                    )
                self.assertEqual(str(ctx.exception), expected_message)


class TypeAnnotationTests(unittest.TestCase):
    def test_function_annotations_exact(self):
        annotations = (
            build_platform_variant_from_execution_result.__annotations__
        )
        self.assertIs(annotations["source"], AdaptationSourceContent)
        self.assertIs(annotations["spec"], PlatformAdaptationSpec)
        self.assertIs(annotations["result"], PlatformAdaptationExecutionResult)
        self.assertIs(annotations["return"], PlatformContentVariant)


class StructuralTests(unittest.TestCase):
    FORBIDDEN_IDENTIFIERS = (
        "TargetPlatform",
        "AdaptationContentKind",
        "get_platform_adaptation_spec",
        "get_platform_adaptation_specs",
        "PlatformAdaptationInstruction",
        "ContentPackageV2",
        "PlatformVariantRef",
        "PackageStage",
        "QualityState",
        "PublicationState",
        "PackageArtifact",
        "image",
        "video",
        "audio",
        "voiceover",
        "subtitle",
        "thumbnail",
        "asset",
        "prompt",
        "messages",
        "model",
        "provider",
        "temperature",
        "executor",
        "openai",
        "anthropic",
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
            ["build_platform_variant_from_execution_result"],
        )
        self.assertEqual(
            [n for n in tree.body if isinstance(n, ast.ClassDef)],
            [],
        )

    def test_exact_all(self):
        self.assertEqual(
            boundary_module.__all__,
            ["build_platform_variant_from_execution_result"],
        )

    def test_imports_exact(self):
        tree = _module_tree()
        imports_from = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
        by_module = {n.module: [a.name for a in n.names] for n in imports_from}
        self.assertEqual(
            by_module,
            {
                "src.content.platform_variant_builder": [
                    "build_platform_content_variant"
                ],
                "src.domain.platform_adaptation": [
                    "AdaptationSourceContent",
                    "PlatformAdaptationSpec",
                    "PlatformContentVariant",
                ],
                "src.domain.platform_adaptation_execution": [
                    "AdaptationExecutionStatus",
                    "PlatformAdaptationExecutionResult",
                ],
            },
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

    def test_exactly_five_if_and_raise_nodes(self):
        tree = _module_tree()
        if_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.If)]
        raise_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]
        self.assertEqual(len(if_nodes), 5)
        self.assertEqual(len(raise_nodes), 5)
        for raise_node in raise_nodes:
            self.assertIsInstance(raise_node.exc, ast.Call)
            self.assertIsInstance(raise_node.exc.func, ast.Name)
            self.assertEqual(raise_node.exc.func.id, "ValueError")

    def test_exact_value_error_messages_in_order(self):
        tree = _module_tree()
        function = next(
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        messages = []
        conditions = []
        for node in ast.walk(function):
            if isinstance(node, ast.If):
                for inner in ast.walk(node.test):
                    if isinstance(inner, ast.Compare):
                        conditions.append(ast.unparse(inner))
                if isinstance(node.body[0], ast.Raise):
                    exc = node.body[0].exc
                    messages.append(exc.args[0].value)
        self.assertEqual(
            messages,
            [
                "candidate_id mismatch",
                "source_content_id mismatch",
                "platform mismatch",
                "content_kind mismatch",
                "execution result is not completed",
            ],
        )
        self.assertEqual(
            conditions,
            [
                "result.candidate_id != source.candidate_id",
                "result.source_content_id != source.content_id",
                "result.platform != spec.platform",
                "result.content_kind != spec.content_kind",
                "result.status is not AdaptationExecutionStatus.COMPLETED",
            ],
        )

    def test_zero_direct_variant_construction(self):
        tree = _module_tree()
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "PlatformContentVariant"
        ]
        self.assertEqual(calls, [])

    def test_exactly_one_builder_call_with_exact_mapping(self):
        tree = _module_tree()
        function = next(
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        calls = [
            n
            for n in ast.walk(function)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "build_platform_content_variant"
        ]
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(len(call.args), 2)
        self.assertEqual(call.args[0].id, "source")
        self.assertEqual(call.args[1].id, "spec")
        keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
        self.assertEqual(set(keywords), {"title", "body", "cta", "language", "metadata"})
        for keyword, attribute in (
            ("title", "title"),
            ("body", "body"),
            ("cta", "cta"),
            ("language", "output_language"),
            ("metadata", "metadata"),
        ):
            node = keywords[keyword]
            self.assertIsInstance(node, ast.Attribute)
            self.assertEqual(node.attr, attribute)
            self.assertIsInstance(node.value, ast.Name)
            self.assertEqual(node.value.id, "result")

    def test_attribute_access_locks(self):
        tree = _module_tree()
        attribute_names = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        self.assertEqual(
            attribute_names & {"candidate_id", "content_id", "source_content_id"},
            {"candidate_id", "content_id", "source_content_id"},
        )
        self.assertEqual(
            attribute_names & {"platform", "content_kind"},
            {"platform", "content_kind"},
        )
        self.assertEqual(
            attribute_names & {"status", "title", "body", "cta", "output_language", "metadata"},
            {"status", "title", "body", "cta", "output_language", "metadata"},
        )
        # Forbidden: source text/link/language and spec policy fields are
        # never accessed in this boundary (18C owns them).
        for forbidden in (
            "cta_link",
            "language",
            "requires_title",
            "allows_external_link",
            "max_characters",
            "structure",
            "tone",
        ):
            self.assertNotIn(forbidden, attribute_names)

    def test_status_gate_uses_identity_comparison(self):
        tree = _module_tree()
        function = next(
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        status_compares = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Compare)
            and any(
                isinstance(op, ast.IsNot) for op in node.ops
            )
        ]
        self.assertEqual(len(status_compares), 1)
        self.assertEqual(len(status_compares[0].ops), 1)


if __name__ == "__main__":
    unittest.main()
