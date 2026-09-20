"""Tests for Stage 18B deterministic platform adaptation policy."""

import ast
import unittest
from dataclasses import FrozenInstanceError

import src.content.platform_adaptation_policy as policy_module
from src.content.platform_adaptation_policy import (
    get_platform_adaptation_spec,
    get_platform_adaptation_specs,
)
from src.domain.platform_adaptation import (
    AdaptationContentKind,
    PlatformAdaptationSpec,
)
from src.domain.strategy import TargetPlatform

MODULE_PATH = "src/content/platform_adaptation_policy.py"


def _module_source() -> str:
    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def _module_tree() -> ast.Module:
    return ast.parse(_module_source(), filename=MODULE_PATH)


class PolicyCoverageTests(unittest.TestCase):
    EXPECTED_POLICY = {
        TargetPlatform.TELEGRAM: PlatformAdaptationSpec(
            platform=TargetPlatform.TELEGRAM,
            content_kind=AdaptationContentKind.TEXT_POST,
            max_characters=None,
            requires_title=True,
            allows_external_link=True,
            structure=("hook", "context", "value", "cta"),
            tone="concise and practical",
        ),
        TargetPlatform.X: PlatformAdaptationSpec(
            platform=TargetPlatform.X,
            content_kind=AdaptationContentKind.TEXT_POST,
            max_characters=280,
            requires_title=False,
            allows_external_link=True,
            structure=("hook", "value", "cta"),
            tone="sharp and concise",
        ),
        TargetPlatform.LINKEDIN: PlatformAdaptationSpec(
            platform=TargetPlatform.LINKEDIN,
            content_kind=AdaptationContentKind.TEXT_POST,
            max_characters=3000,
            requires_title=False,
            allows_external_link=True,
            structure=(
                "hook",
                "context",
                "insight",
                "practical_takeaway",
                "cta",
            ),
            tone="professional and practical",
        ),
        TargetPlatform.REDDIT: PlatformAdaptationSpec(
            platform=TargetPlatform.REDDIT,
            content_kind=AdaptationContentKind.TEXT_POST,
            max_characters=None,
            requires_title=True,
            allows_external_link=False,
            structure=("title", "context", "details", "discussion"),
            tone="informative and conversational",
        ),
        TargetPlatform.YOUTUBE_SHORTS: PlatformAdaptationSpec(
            platform=TargetPlatform.YOUTUBE_SHORTS,
            content_kind=AdaptationContentKind.SHORT_VIDEO_SCRIPT,
            max_characters=None,
            requires_title=True,
            allows_external_link=False,
            structure=("hook", "setup", "value", "payoff"),
            tone="fast-paced and clear",
        ),
        TargetPlatform.TIKTOK: PlatformAdaptationSpec(
            platform=TargetPlatform.TIKTOK,
            content_kind=AdaptationContentKind.SHORT_VIDEO_SCRIPT,
            max_characters=None,
            requires_title=False,
            allows_external_link=False,
            structure=("hook", "setup", "value", "payoff"),
            tone="direct and energetic",
        ),
        TargetPlatform.PINTEREST: PlatformAdaptationSpec(
            platform=TargetPlatform.PINTEREST,
            content_kind=AdaptationContentKind.PIN_COPY,
            max_characters=500,
            requires_title=True,
            allows_external_link=True,
            structure=("title", "description", "cta"),
            tone="descriptive and actionable",
        ),
    }

    def test_all_platforms_covered_exact_set(self):
        self.assertEqual(set(policy_module._PLATFORM_ADAPTATION_POLICY), set(self.EXPECTED_POLICY))

    def test_policy_matches_target_platform_members_exactly(self):
        self.assertEqual(
            set(policy_module._PLATFORM_ADAPTATION_POLICY),
            set(TargetPlatform),
        )
        self.assertEqual(
            len(policy_module._PLATFORM_ADAPTATION_POLICY),
            len(set(TargetPlatform)),
        )

    def test_telegram_exact_spec(self):
        self.assertEqual(
            get_platform_adaptation_spec(TargetPlatform.TELEGRAM),
            self.EXPECTED_POLICY[TargetPlatform.TELEGRAM],
        )

    def test_x_exact_spec(self):
        spec = get_platform_adaptation_spec(TargetPlatform.X)
        self.assertIs(spec.content_kind, AdaptationContentKind.TEXT_POST)
        self.assertEqual(spec.max_characters, 280)
        self.assertFalse(spec.requires_title)
        self.assertTrue(spec.allows_external_link)
        self.assertEqual(spec.structure, ("hook", "value", "cta"))
        self.assertEqual(spec.tone, "sharp and concise")

    def test_linkedin_exact_spec(self):
        spec = get_platform_adaptation_spec(TargetPlatform.LINKEDIN)
        self.assertIs(spec.content_kind, AdaptationContentKind.TEXT_POST)
        self.assertEqual(spec.max_characters, 3000)
        self.assertFalse(spec.requires_title)
        self.assertTrue(spec.allows_external_link)
        self.assertEqual(
            spec.structure,
            ("hook", "context", "insight", "practical_takeaway", "cta"),
        )
        self.assertEqual(spec.tone, "professional and practical")

    def test_reddit_exact_spec(self):
        spec = get_platform_adaptation_spec(TargetPlatform.REDDIT)
        self.assertIs(spec.content_kind, AdaptationContentKind.TEXT_POST)
        self.assertIsNone(spec.max_characters)
        self.assertTrue(spec.requires_title)
        self.assertFalse(spec.allows_external_link)
        self.assertEqual(
            spec.structure,
            ("title", "context", "details", "discussion"),
        )
        self.assertEqual(spec.tone, "informative and conversational")

    def test_youtube_shorts_exact_spec(self):
        spec = get_platform_adaptation_spec(TargetPlatform.YOUTUBE_SHORTS)
        self.assertIs(spec.content_kind, AdaptationContentKind.SHORT_VIDEO_SCRIPT)
        self.assertIsNone(spec.max_characters)
        self.assertTrue(spec.requires_title)
        self.assertFalse(spec.allows_external_link)
        self.assertEqual(spec.structure, ("hook", "setup", "value", "payoff"))
        self.assertEqual(spec.tone, "fast-paced and clear")

    def test_tiktok_exact_spec(self):
        spec = get_platform_adaptation_spec(TargetPlatform.TIKTOK)
        self.assertIs(spec.content_kind, AdaptationContentKind.SHORT_VIDEO_SCRIPT)
        self.assertIsNone(spec.max_characters)
        self.assertFalse(spec.requires_title)
        self.assertFalse(spec.allows_external_link)
        self.assertEqual(spec.structure, ("hook", "setup", "value", "payoff"))
        self.assertEqual(spec.tone, "direct and energetic")

    def test_pinterest_exact_spec(self):
        spec = get_platform_adaptation_spec(TargetPlatform.PINTEREST)
        self.assertIs(spec.content_kind, AdaptationContentKind.PIN_COPY)
        self.assertEqual(spec.max_characters, 500)
        self.assertTrue(spec.requires_title)
        self.assertTrue(spec.allows_external_link)
        self.assertEqual(spec.structure, ("title", "description", "cta"))
        self.assertEqual(spec.tone, "descriptive and actionable")

    def test_platform_field_matches_key(self):
        for platform in TargetPlatform:
            with self.subTest(platform=platform):
                spec = get_platform_adaptation_spec(platform)
                self.assertIs(spec.platform, platform)

    def test_content_kind_groups(self):
        groups: dict[AdaptationContentKind, list] = {
            kind: [] for kind in AdaptationContentKind
        }
        for platform in TargetPlatform:
            spec = get_platform_adaptation_spec(platform)
            groups[spec.content_kind].append(platform)
        self.assertEqual(
            set(groups[AdaptationContentKind.TEXT_POST]),
            {
                TargetPlatform.TELEGRAM,
                TargetPlatform.X,
                TargetPlatform.LINKEDIN,
                TargetPlatform.REDDIT,
            },
        )
        self.assertEqual(
            set(groups[AdaptationContentKind.SHORT_VIDEO_SCRIPT]),
            {TargetPlatform.YOUTUBE_SHORTS, TargetPlatform.TIKTOK},
        )
        self.assertEqual(
            set(groups[AdaptationContentKind.PIN_COPY]),
            {TargetPlatform.PINTEREST},
        )

    def test_external_link_policy(self):
        for platform in TargetPlatform:
            spec = get_platform_adaptation_spec(platform)
            with self.subTest(platform=platform):
                if platform in (TargetPlatform.TELEGRAM, TargetPlatform.X, TargetPlatform.LINKEDIN, TargetPlatform.PINTEREST):
                    self.assertTrue(spec.allows_external_link)
                else:
                    self.assertFalse(spec.allows_external_link)

    def test_title_policy(self):
        for platform in TargetPlatform:
            spec = get_platform_adaptation_spec(platform)
            with self.subTest(platform=platform):
                if platform in (TargetPlatform.TELEGRAM, TargetPlatform.REDDIT, TargetPlatform.YOUTUBE_SHORTS, TargetPlatform.PINTEREST):
                    self.assertTrue(spec.requires_title)
                else:
                    self.assertFalse(spec.requires_title)

    def test_max_character_policy(self):
        expected = {
            TargetPlatform.TELEGRAM: None,
            TargetPlatform.X: 280,
            TargetPlatform.LINKEDIN: 3000,
            TargetPlatform.REDDIT: None,
            TargetPlatform.YOUTUBE_SHORTS: None,
            TargetPlatform.TIKTOK: None,
            TargetPlatform.PINTEREST: 500,
        }
        for platform, max_characters in expected.items():
            with self.subTest(platform=platform):
                self.assertEqual(
                    get_platform_adaptation_spec(platform).max_characters,
                    max_characters,
                )

    def test_exact_policy_data_structural_lock(self):
        for platform, expected_spec in self.EXPECTED_POLICY.items():
            with self.subTest(platform=platform):
                self.assertEqual(get_platform_adaptation_spec(platform), expected_spec)
                self.assertIs(
                    get_platform_adaptation_spec(platform).content_kind,
                    expected_spec.content_kind,
                )


class LookupBehaviorTests(unittest.TestCase):
    def test_single_lookup_identity(self):
        for platform in TargetPlatform:
            first = get_platform_adaptation_spec(platform)
            second = get_platform_adaptation_spec(platform)
            with self.subTest(platform=platform):
                self.assertIs(first, second)

    def test_single_lookup_returns_stored_object(self):
        for platform in TargetPlatform:
            with self.subTest(platform=platform):
                self.assertIs(
                    get_platform_adaptation_spec(platform),
                    policy_module._PLATFORM_ADAPTATION_POLICY[platform],
                )

    def test_tuple_lookup_order(self):
        result = get_platform_adaptation_specs(
            (
                TargetPlatform.PINTEREST,
                TargetPlatform.X,
                TargetPlatform.TELEGRAM,
            )
        )
        self.assertEqual(
            [spec.platform for spec in result],
            [
                TargetPlatform.PINTEREST,
                TargetPlatform.X,
                TargetPlatform.TELEGRAM,
            ],
        )

    def test_duplicates_preserved(self):
        result = get_platform_adaptation_specs(
            (
                TargetPlatform.X,
                TargetPlatform.TELEGRAM,
                TargetPlatform.X,
            )
        )
        self.assertEqual(len(result), 3)
        self.assertEqual(
            [spec.platform for spec in result],
            [TargetPlatform.X, TargetPlatform.TELEGRAM, TargetPlatform.X],
        )
        self.assertIs(result[0], result[2])

    def test_empty_tuple(self):
        self.assertEqual(get_platform_adaptation_specs(()), ())

    def test_invalid_key_natural_key_error(self):
        # A genuinely unknown key must fail naturally through direct dict
        # indexing: no fallback, no default spec, no caught KeyError.
        with self.assertRaises(KeyError):
            get_platform_adaptation_spec("not-a-platform")  # type: ignore[arg-type]

    def test_strenum_string_equality_is_language_semantics_not_coercion(self):
        # NOTE: TargetPlatform is a StrEnum, so a plain string equal to a
        # member value compares and hashes identically to that member; dict
        # lookup matches it without any coercion code in this module (no
        # .get, no try/except, no conversion — structurally proven).
        # The natural-failure guarantee is therefore tested with a key that
        # matches no member, and this behavior is documented deliberately.
        self.assertEqual(TargetPlatform.TELEGRAM, "telegram")
        spec = get_platform_adaptation_spec("telegram")  # type: ignore[arg-type]
        self.assertIs(spec.platform, TargetPlatform.TELEGRAM)

    def test_policy_object_immutability(self):
        spec = get_platform_adaptation_spec(TargetPlatform.X)
        with self.assertRaises(FrozenInstanceError):
            spec.max_characters = 999

    def test_determinism(self):
        platforms = (TargetPlatform.TELEGRAM, TargetPlatform.TIKTOK)
        first = get_platform_adaptation_specs(platforms)
        second = get_platform_adaptation_specs(platforms)
        self.assertEqual(first, second)
        for a, b in zip(first, second):
            self.assertIs(a, b)


class StructuralTests(unittest.TestCase):
    FORBIDDEN_IDENTIFIERS = (
        "AdaptationSourceContent",
        "PlatformContentVariant",
        "StrategistPlan",
        "ContentCandidate",
        "ContentFormat",
        "ContentCluster",
        "ContentPackageV2",
        "PlatformVariantRef",
        "PackageStage",
        "QualityState",
        "PublicationState",
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
        "telegram",
        "tweepy",
        "linkedin",
        "reddit",
        "pinterest",
        "youtube",
        "tiktok",
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

    def test_exactly_two_module_level_functions(self):
        tree = _module_tree()
        functions = [
            n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual(
            [f.name for f in functions],
            ["get_platform_adaptation_spec", "get_platform_adaptation_specs"],
        )

    def test_exact_all(self):
        self.assertEqual(
            policy_module.__all__,
            ["get_platform_adaptation_spec", "get_platform_adaptation_specs"],
        )

    def test_exactly_one_private_mapping_with_seven_entries(self):
        tree = _module_tree()
        module_assigns = [
            n
            for n in tree.body
            if isinstance(n, (ast.Assign, ast.AnnAssign))
            and (
                (
                    isinstance(n.target, ast.Name)
                    and n.target.id == "_PLATFORM_ADAPTATION_POLICY"
                )
                if isinstance(n, ast.AnnAssign)
                else any(
                    isinstance(t, ast.Name) and t.id == "_PLATFORM_ADAPTATION_POLICY"
                    for t in n.targets
                )
            )
        ]
        self.assertEqual(len(module_assigns), 1)
        self.assertIsInstance(module_assigns[0].value, ast.Dict)
        self.assertEqual(len(module_assigns[0].value.keys), 7)

    def test_every_target_platform_member_is_a_key_exactly_once(self):
        policy = policy_module._PLATFORM_ADAPTATION_POLICY
        self.assertEqual(set(policy), set(TargetPlatform))
        self.assertEqual(len(policy), len(set(TargetPlatform)))

    def test_exactly_seven_spec_construction_sites(self):
        tree = _module_tree()
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "PlatformAdaptationSpec"
        ]
        self.assertEqual(len(calls), 7)

    def test_no_forbidden_identifiers(self):
        identifiers = self._collect_identifier_nodes(_module_tree())
        for forbidden in self.FORBIDDEN_IDENTIFIERS:
            self.assertNotIn(forbidden, identifiers)

    def test_no_get_fallback_on_policy_mapping(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "get":
                self.fail("policy mapping uses .get(...) fallback")

    def test_no_try_no_validation_no_assert(self):
        source = _module_source()
        self.assertNotIn("assert ", source)
        for token in ("ValueError", "TypeError"):
            self.assertNotIn(token, source)
        for node in ast.walk(_module_tree()):
            self.assertNotIsInstance(node, ast.Try)

    def test_no_sorting_set_dedup_len_or_slicing(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(
                    node.func.id,
                    {"sorted", "set", "len", "reversed", "deduplicate"},
                )
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
                self.fail("text slicing present in production module")

    def test_no_source_content_field_access_or_variant_identity(self):
        tree = _module_tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotIn(
                    node.attr,
                    {
                        "title",
                        "body",
                        "cta_link",
                        "language",
                        "metadata",
                        "variant_id",
                        "source_content_id",
                    },
                )

    def test_direct_indexing_in_spec_lookup(self):
        tree = _module_tree()
        functions = {
            n.name: n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        spec_fn = functions["get_platform_adaptation_spec"]
        subscripts = [
            n
            for n in ast.walk(spec_fn)
            if isinstance(n, ast.Subscript)
            and isinstance(n.value, ast.Name)
            and n.value.id == "_PLATFORM_ADAPTATION_POLICY"
        ]
        self.assertEqual(len(subscripts), 1)

    def test_specs_function_shape(self):
        tree = _module_tree()
        functions = {
            n.name: n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        specs_fn = functions["get_platform_adaptation_specs"]
        for node in ast.walk(specs_fn):
            self.assertNotIsInstance(node, (ast.If, ast.IfExp))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"set", "sorted"})
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "get_platform_adaptation_spec"
                for node in ast.walk(specs_fn)
            )
        )


if __name__ == "__main__":
    unittest.main()
