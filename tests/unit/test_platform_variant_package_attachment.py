"""Tests for Stage 18E-B content package platform-variant attachment boundary."""

import ast
import inspect
import unittest

import src.content.platform_variant_package_attachment as attachment_module
from src.content.platform_variant_package_attachment import (
    attach_adapted_platform_variant,
)
from src.domain.content_package import (
    ContentPackageV2,
    PackageStage,
    PlatformVariantRef,
    PublicationState,
    QualityState,
    SourceProvenance,
)
from src.domain.platform_adaptation import (
    AdaptationContentKind,
    PlatformContentVariant,
)
from src.domain.strategy import (
    ContentCluster,
    ContentFormat,
    TargetPlatform,
)
from src.domain.strategist import StrategistPlan

MODULE_PATH = "src/content/platform_variant_package_attachment.py"


def _module_source() -> str:
    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _module_tree() -> ast.Module:
    return ast.parse(_module_source(), filename=MODULE_PATH)


def _make_strategy(**overrides) -> StrategistPlan:
    values = dict(
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
        structure=("problem", "tool", "cta"),
        language="ru",
        mode="growth",
    )
    values.update(overrides)
    return StrategistPlan(**values)


def _make_provenance() -> SourceProvenance:
    return SourceProvenance(
        candidate_id="cand-123",
        source_url="https://example.com/tool",
        source_name="example",
        source_type="github",
        discovered_at="2026-09-19T10:00:00+00:00",
        published_at="2026-09-19T09:00:00+00:00",
        verification_status="verified",
        verification_confidence=0.91,
    )


def _make_package(**overrides) -> ContentPackageV2:
    values = dict(
        package_id="pkg-123",
        candidate_id="cand-123",
        strategy=_make_strategy(),
        provenance=_make_provenance(),
        stage=PackageStage.ADAPTATION_PENDING,
        quality_state=QualityState.NOT_CHECKED,
        publication_state=PublicationState.NOT_READY,
        artifacts=(),
        platform_variants=(),
        analytics_links=(),
        created_at="2026-09-19T10:00:00+00:00",
        updated_at="2026-09-19T10:00:00+00:00",
        legacy_content_id=None,
    )
    values.update(overrides)
    return ContentPackageV2(**values)


def _make_variant(**overrides) -> PlatformContentVariant:
    values = dict(
        variant_id="content-123:telegram",
        candidate_id="cand-123",
        source_content_id="content-123",
        platform=TargetPlatform.TELEGRAM,
        content_kind=AdaptationContentKind.TEXT_POST,
        title="title",
        body="body",
        cta="cta",
        cta_link="https://example.com",
        language="ru",
        metadata={},
    )
    values.update(overrides)
    return PlatformContentVariant(**values)


def _make_ref(**overrides) -> PlatformVariantRef:
    values = dict(
        variant_id="content-123:telegram",
        platform=TargetPlatform.TELEGRAM,
        content_ref="memory://variant/telegram",
        quality_state=QualityState.NOT_CHECKED,
        publication_state=PublicationState.NOT_READY,
    )
    values.update(overrides)
    return PlatformVariantRef(**values)


class HappyPathTests(unittest.TestCase):
    def test_happy_path(self):
        package = _make_package()
        variant = _make_variant()
        ref = _make_ref()
        result = attach_adapted_platform_variant(
            package,
            variant,
            ref,
            updated_at="2026-09-20T12:00:00+00:00",
        )
        self.assertIsInstance(result, ContentPackageV2)
        self.assertIsNot(result, package)
        self.assertEqual(package.platform_variants, ())
        self.assertEqual(result.platform_variants, (ref,))
        self.assertIs(result.platform_variants[0], ref)
        self.assertEqual(result.updated_at, "2026-09-20T12:00:00+00:00")

    def test_stage_remains_adaptation_pending(self):
        package = _make_package()
        result = attach_adapted_platform_variant(
            package, _make_variant(), _make_ref(), updated_at="t2"
        )
        self.assertIs(result.stage, PackageStage.ADAPTATION_PENDING)
        self.assertIs(package.stage, PackageStage.ADAPTATION_PENDING)

    def test_strategy_provenance_identity_preserved(self):
        package = _make_package()
        result = attach_adapted_platform_variant(
            package, _make_variant(), _make_ref(), updated_at="t2"
        )
        self.assertIs(result.strategy, package.strategy)
        self.assertIs(result.provenance, package.provenance)

    def test_other_package_fields_preserved(self):
        package = _make_package()
        result = attach_adapted_platform_variant(
            package, _make_variant(), _make_ref(), updated_at="t2"
        )
        self.assertEqual(result.package_id, package.package_id)
        self.assertEqual(result.candidate_id, package.candidate_id)
        self.assertIs(result.quality_state, package.quality_state)
        self.assertIs(result.publication_state, package.publication_state)
        self.assertEqual(result.artifacts, package.artifacts)
        self.assertEqual(result.analytics_links, package.analytics_links)
        self.assertEqual(result.created_at, package.created_at)
        self.assertEqual(result.legacy_content_id, package.legacy_content_id)

    def test_all_target_platforms_accepted(self):
        for platform in (TargetPlatform.TELEGRAM, TargetPlatform.X):
            with self.subTest(platform=platform):
                package = _make_package()
                variant = _make_variant(
                    variant_id=f"content-123:{platform.value}",
                    platform=platform,
                )
                ref = _make_ref(
                    variant_id=f"content-123:{platform.value}",
                    platform=platform,
                )
                result = attach_adapted_platform_variant(
                    package, variant, ref, updated_at="t2"
                )
                self.assertEqual(result.platform_variants, (ref,))


class RejectionTests(unittest.TestCase):
    def test_all_non_adaptation_pending_stages_rejected(self):
        variant = _make_variant()
        ref = _make_ref()
        for stage in PackageStage:
            if stage is PackageStage.ADAPTATION_PENDING:
                continue
            with self.subTest(stage=stage):
                package = _make_package(stage=stage)
                with self.assertRaises(ValueError) as ctx:
                    attach_adapted_platform_variant(package, variant, ref, updated_at="t2")
                self.assertEqual(str(ctx.exception), "package is not adaptation pending")

    def test_candidate_mismatch(self):
        with self.assertRaises(ValueError) as ctx:
            attach_adapted_platform_variant(
                _make_package(),
                _make_variant(candidate_id="cand-other"),
                _make_ref(),
                updated_at="t2",
            )
        self.assertEqual(str(ctx.exception), "candidate_id mismatch")

    def test_non_target_platform(self):
        with self.assertRaises(ValueError) as ctx:
            attach_adapted_platform_variant(
                _make_package(),
                _make_variant(
                    variant_id="content-123:reddit",
                    platform=TargetPlatform.REDDIT,
                ),
                _make_ref(
                    variant_id="content-123:reddit",
                    platform=TargetPlatform.REDDIT,
                ),
                updated_at="t2",
            )
        self.assertEqual(
            str(ctx.exception),
            "platform is not targeted by package strategy",
        )

    def test_variant_id_mismatch(self):
        with self.assertRaises(ValueError) as ctx:
            attach_adapted_platform_variant(
                _make_package(),
                _make_variant(variant_id="variant-A"),
                _make_ref(variant_id="variant-B"),
                updated_at="t2",
            )
        self.assertEqual(str(ctx.exception), "variant_id mismatch")

    def test_ref_platform_mismatch(self):
        with self.assertRaises(ValueError) as ctx:
            attach_adapted_platform_variant(
                _make_package(),
                _make_variant(platform=TargetPlatform.TELEGRAM),
                _make_ref(platform=TargetPlatform.X),
                updated_at="t2",
            )
        self.assertEqual(str(ctx.exception), "platform mismatch")

    def test_noninitial_quality_state_rejected(self):
        for quality_state in QualityState:
            if quality_state is QualityState.NOT_CHECKED:
                continue
            with self.subTest(quality_state=quality_state):
                with self.assertRaises(ValueError) as ctx:
                    attach_adapted_platform_variant(
                        _make_package(),
                        _make_variant(),
                        _make_ref(quality_state=quality_state),
                        updated_at="t2",
                    )
                self.assertEqual(
                    str(ctx.exception),
                    "variant ref quality state is not initial",
                )

    def test_noninitial_publication_state_rejected(self):
        for publication_state in PublicationState:
            if publication_state is PublicationState.NOT_READY:
                continue
            with self.subTest(publication_state=publication_state):
                with self.assertRaises(ValueError) as ctx:
                    attach_adapted_platform_variant(
                        _make_package(),
                        _make_variant(),
                        _make_ref(publication_state=publication_state),
                        updated_at="t2",
                    )
                self.assertEqual(
                    str(ctx.exception),
                    "variant ref publication state is not initial",
                )

    def test_duplicate_platform_rejected_with_different_ids(self):
        package = _make_package(
            platform_variants=(
                _make_ref(
                    variant_id="old-telegram",
                    platform=TargetPlatform.TELEGRAM,
                    content_ref="old",
                ),
            )
        )
        with self.assertRaises(ValueError) as ctx:
            attach_adapted_platform_variant(
                package,
                _make_variant(variant_id="new-telegram"),
                _make_ref(variant_id="new-telegram"),
                updated_at="t2",
            )
        self.assertEqual(str(ctx.exception), "duplicate platform variant")

    def test_validation_order(self):
        # Each case makes exactly ONE earlier-in-order check fail first while
        # every LATER check would also fail if reached. This locks precedence.
        package = _make_package()
        variant = _make_variant()
        ref = _make_ref()

        late_failures = dict(
            candidate_id="cand-other",  # candidate mismatch
            platform=TargetPlatform.LINKEDIN,  # non-target + ref mismatches
        )

        def late_variant(**overrides):
            values = dict(
                candidate_id="cand-other",
                variant_id="variant-Z:linkedin",
                platform=TargetPlatform.LINKEDIN,
            )
            values.update(overrides)
            return _make_variant(**values)

        def late_ref(**overrides):
            values = dict(
                variant_id="variant-W:linkedin",
                platform=TargetPlatform.TIKTOK,
                quality_state=QualityState.PENDING,
                publication_state=PublicationState.READY,
            )
            values.update(overrides)
            return _make_ref(**values)

        cases = [
            # 1. wrong stage + candidate mismatch + non-target platform +
            #    id/platform/state mismatches -> stage message wins.
            (
                "package is not adaptation pending",
                _make_package(stage=PackageStage.PUBLISHED),
                late_variant(),
                late_ref(),
            ),
            # 2. stage valid; candidate mismatch + all later failures.
            (
                "candidate_id mismatch",
                package,
                late_variant(),
                late_ref(),
            ),
            # 3. stage/candidate valid; non-target platform + later failures.
            (
                "platform is not targeted by package strategy",
                package,
                _make_variant(
                    variant_id="content-123:linkedin",
                    platform=TargetPlatform.LINKEDIN,
                ),
                late_ref(),
            ),
            # 4. stage/candidate/platform-membership valid (targeted platform);
            #    variant_id mismatch + later failures.
            (
                "variant_id mismatch",
                package,
                _make_variant(),
                _make_ref(variant_id="variant-B"),
            ),
            # 5. ids correlate; ref platform mismatch + state failures.
            (
                "platform mismatch",
                package,
                _make_variant(),
                _make_ref(platform=TargetPlatform.X),
            ),
            # 6. everything correlated; quality state noninitial.
            (
                "variant ref quality state is not initial",
                package,
                _make_variant(),
                _make_ref(quality_state=QualityState.PENDING),
            ),
            # 7. quality initial; publication state noninitial.
            (
                "variant ref publication state is not initial",
                package,
                _make_variant(),
                _make_ref(publication_state=PublicationState.READY),
            ),
            # 8. all gates pass; duplicate platform in package.
            (
                "duplicate platform variant",
                _make_package(
                    platform_variants=(
                        _make_ref(
                            variant_id="old-telegram",
                            platform=TargetPlatform.TELEGRAM,
                        ),
                    )
                ),
                _make_variant(),
                _make_ref(),
            ),
        ]
        for expected_message, case_package, case_variant, case_ref in cases:
            with self.subTest(expected=expected_message):
                with self.assertRaises(ValueError) as ctx:
                    attach_adapted_platform_variant(
                        case_package, case_variant, case_ref, updated_at="t2"
                    )
                self.assertEqual(str(ctx.exception), expected_message)


class IndifferenceAndPassthroughTests(unittest.TestCase):
    def test_different_existing_platform_allowed(self):
        package = _make_package(
            platform_variants=(
                _make_ref(
                    variant_id="content-123:x",
                    platform=TargetPlatform.X,
                ),
            )
        )
        ref = _make_ref()
        result = attach_adapted_platform_variant(
            package,
            _make_variant(),
            ref,
            updated_at="t2",
        )
        self.assertEqual(result.platform_variants, (package.platform_variants[0], ref))
        self.assertIs(result.platform_variants[1], ref)

    def test_content_ref_not_inspected(self):
        for content_ref in ("", " opaque ", "\nref\n"):
            with self.subTest(content_ref=content_ref):
                package = _make_package()
                result = attach_adapted_platform_variant(
                    package,
                    _make_variant(),
                    _make_ref(content_ref=content_ref),
                    updated_at="t2",
                )
                self.assertEqual(result.platform_variants[0].content_ref, content_ref)

    def test_updated_at_passthrough(self):
        for updated_at in ("", "timestamp", "  timestamp  "):
            with self.subTest(updated_at=updated_at):
                package = _make_package()
                result = attach_adapted_platform_variant(
                    package, _make_variant(), _make_ref(), updated_at=updated_at
                )
                self.assertEqual(result.updated_at, updated_at)

    def test_variant_source_content_id_ignored(self):
        for source_content_id in ("", "unrelated-content", "anything"):
            with self.subTest(source_content_id=source_content_id):
                package = _make_package()
                result = attach_adapted_platform_variant(
                    package,
                    _make_variant(source_content_id=source_content_id),
                    _make_ref(),
                    updated_at="t2",
                )
                self.assertEqual(len(result.platform_variants), 1)

    def test_variant_content_fields_ignored(self):
        package = _make_package()
        result = attach_adapted_platform_variant(
            package,
            _make_variant(
                content_kind=AdaptationContentKind.PIN_COPY,
                title="different",
                body="different",
                cta="different",
                cta_link="different",
                language="en",
                metadata={"different": True},
            ),
            _make_ref(),
            updated_at="t2",
        )
        self.assertEqual(len(result.platform_variants), 1)

    def test_immutable_package_behavior(self):
        package = _make_package()
        snapshot = package
        result = attach_adapted_platform_variant(
            package, _make_variant(), _make_ref(), updated_at="t2"
        )
        self.assertIs(package, snapshot)
        self.assertEqual(package.platform_variants, ())
        self.assertIsNot(result, package)


class SignatureTests(unittest.TestCase):
    def test_signature_exact(self):
        signature = inspect.signature(attach_adapted_platform_variant)
        parameters = list(signature.parameters.values())
        self.assertEqual(
            [p.name for p in parameters],
            ["package", "variant", "variant_ref", "updated_at"],
        )
        by_name = {p.name: p for p in parameters}
        for name in ("package", "variant", "variant_ref"):
            self.assertEqual(by_name[name].kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        updated_at = by_name["updated_at"]
        self.assertEqual(updated_at.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(updated_at.annotation, str)
        self.assertIs(updated_at.default, inspect.Parameter.empty)
        self.assertIs(by_name["package"].annotation, ContentPackageV2)
        self.assertIs(by_name["variant"].annotation, PlatformContentVariant)
        self.assertIs(by_name["variant_ref"].annotation, PlatformVariantRef)
        self.assertIs(signature.return_annotation, ContentPackageV2)


class StructuralTests(unittest.TestCase):
    FORBIDDEN_IDENTIFIERS = (
        "TargetPlatform",
        "AdaptationContentKind",
        "StrategistPlan",
        "PlatformAdaptationSpec",
        "PlatformAdaptationExecutionResult",
        "PlatformAdaptationInstruction",
        "build_platform_variant_ref",
        "transition_package_stage",
        "get_platform_adaptation_spec",
        "get_platform_adaptation_specs",
        "VARIANTS_READY",
        "package_id",
        "provenance",
        "artifacts",
        "analytics_links",
        "created_at",
        "legacy_content_id",
        "source_content_id",
        "content_kind",
        "title",
        "body",
        "cta",
        "cta_link",
        "language",
        "metadata",
        "content_ref",
        "replace",
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
        "gemini",
        "groq",
        "prompt",
        "model",
        "provider",
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

    def test_exactly_one_module_level_function_and_no_classes(self):
        tree = _module_tree()
        functions = [
            n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(
            [f.name for f in functions],
            ["attach_adapted_platform_variant"],
        )
        self.assertEqual(
            [n for n in tree.body if isinstance(n, ast.ClassDef)],
            [],
        )

    def test_exact_all(self):
        self.assertEqual(
            attachment_module.__all__,
            ["attach_adapted_platform_variant"],
        )

    def test_imports_exact(self):
        tree = _module_tree()
        imports_from = [n for n in tree.body if isinstance(n, ast.ImportFrom)]
        by_module = {n.module: [a.name for a in n.names] for n in imports_from}
        self.assertEqual(
            by_module,
            {
                "src.content.content_package_lifecycle": ["attach_platform_variant"],
                "src.domain.content_package": [
                    "ContentPackageV2",
                    "PackageStage",
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

    def test_control_flow_shape(self):
        tree = _module_tree()
        if_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.If)]
        raise_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]
        for_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.For)]
        self.assertEqual(len(if_nodes), 8)
        self.assertEqual(len(raise_nodes), 8)
        self.assertEqual(len(for_nodes), 1)
        for raise_node in raise_nodes:
            self.assertIsInstance(raise_node.exc, ast.Call)
            self.assertIsInstance(raise_node.exc.func, ast.Name)
            self.assertEqual(raise_node.exc.func.id, "ValueError")

    def test_exact_messages_in_order(self):
        tree = _module_tree()
        function = next(
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        messages = []
        for node in ast.walk(function):
            if isinstance(node, ast.If) and isinstance(node.body[0], ast.Raise):
                messages.append(node.body[0].exc.args[0].value)
        self.assertEqual(
            messages,
            [
                "package is not adaptation pending",
                "candidate_id mismatch",
                "platform is not targeted by package strategy",
                "variant_id mismatch",
                "platform mismatch",
                "variant ref quality state is not initial",
                "variant ref publication state is not initial",
                "duplicate platform variant",
            ],
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

    def test_attribute_access_locks(self):
        tree = _module_tree()
        attribute_names = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        # package: stage, candidate_id, strategy(target_platforms),
        # platform_variants (loop). variant: candidate_id, platform,
        # variant_id. variant_ref: variant_id, platform, quality_state,
        # publication_state.
        self.assertEqual(
            attribute_names & {"stage", "candidate_id", "strategy", "platform_variants", "target_platforms"},
            {"stage", "candidate_id", "strategy", "platform_variants", "target_platforms"},
        )
        self.assertEqual(
            attribute_names & {"variant_id", "platform", "quality_state", "publication_state"},
            {"variant_id", "platform", "quality_state", "publication_state"},
        )

    def test_only_adaptation_pending_member_referenced(self):
        tree = _module_tree()
        attribute_names = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
        }
        stage_members = attribute_names & {member.name for member in PackageStage}
        self.assertEqual(stage_members, {"ADAPTATION_PENDING"})

    def test_delegation_lock(self):
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
            and n.func.id == "attach_platform_variant"
        ]
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(len(call.args), 2)
        self.assertEqual(call.args[0].id, "package")
        self.assertEqual(call.args[1].id, "variant_ref")
        self.assertEqual(len(call.keywords), 1)
        self.assertEqual(call.keywords[0].arg, "updated_at")
        self.assertEqual(call.keywords[0].value.id, "updated_at")

    def test_no_direct_package_construction_or_replace(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, ast.Try)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotEqual(node.func.attr, "replace")


if __name__ == "__main__":
    unittest.main()
