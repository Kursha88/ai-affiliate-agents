"""Unit tests for Config.get_research_config() (Step 13C).

Focused tests for exactly the specified behaviors: empty-config
defaults, mapping validation, forwarding into LiveResearchConfig,
single get_settings() call, unchanged parser-error propagation, and the
structural boundaries of the new method plus the untouched
get_settings() implementation. unittest + mock only; the real
settings.yaml is NEVER read (get_settings is always patched).
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import Config  # noqa: E402
from src.research.adapters.rss import OfficialFeed  # noqa: E402
from src.research.live_config import LiveResearchConfig  # noqa: E402

CONFIG_PY = PROJECT_ROOT / "src" / "core" / "config.py"

VALID_RESEARCH = {
    "trusted_primary_domains": ["Example.com"],
    "official_blog_feeds": [
        {
            "name": "Example Blog",
            "feed_url": "https://example.com/feed.xml",
            "trusted_domain": "example.com",
        }
    ],
    "official_docs_feeds": [
        {
            "name": "Example Docs",
            "feed_url": "https://docs.example.com/feed.xml",
            "trusted_domain": "docs.example.com",
        }
    ],
}


class TestGetResearchConfig(unittest.TestCase):
    """Runtime behavior of Config.get_research_config()."""

    def _patch_settings(self, value):
        """Patch Config.get_settings with a fixed return value."""
        patcher = mock.patch.object(Config, "get_settings", return_value=value)
        patched = patcher.start()
        self.addCleanup(patcher.stop)
        return patched

    def test_missing_research_key_returns_empty_config(self) -> None:
        self._patch_settings({})
        config = Config.get_research_config()
        self.assertIsInstance(config, LiveResearchConfig)
        self.assertEqual(config.blog_feeds, ())
        self.assertEqual(config.docs_feeds, ())
        self.assertEqual(config.trusted_primary_domains, ())

    def test_research_none_returns_empty_config(self) -> None:
        self._patch_settings({"research": None})
        config = Config.get_research_config()
        self.assertEqual(config.blog_feeds, ())
        self.assertEqual(config.docs_feeds, ())
        self.assertEqual(config.trusted_primary_domains, ())

    def test_valid_research_mapping_forwarded_to_parser(self) -> None:
        self._patch_settings({"research": VALID_RESEARCH})
        config = Config.get_research_config()
        # Trusted domain normalized (strip + lowercase).
        self.assertEqual(config.trusted_primary_domains, ("example.com",))
        # Exactly one blog feed with correct values.
        self.assertEqual(len(config.blog_feeds), 1)
        blog = config.blog_feeds[0]
        self.assertIsInstance(blog, OfficialFeed)
        self.assertEqual(blog.name, "Example Blog")
        self.assertEqual(blog.feed_url, "https://example.com/feed.xml")
        self.assertEqual(blog.trusted_domain, "example.com")
        # Exactly one docs feed with correct values.
        self.assertEqual(len(config.docs_feeds), 1)
        docs = config.docs_feeds[0]
        self.assertIsInstance(docs, OfficialFeed)
        self.assertEqual(docs.name, "Example Docs")
        self.assertEqual(docs.feed_url, "https://docs.example.com/feed.xml")
        self.assertEqual(docs.trusted_domain, "docs.example.com")

    def test_get_settings_called_exactly_once(self) -> None:
        patched = self._patch_settings({})
        Config.get_research_config()
        self.assertEqual(patched.call_count, 1)

    def test_invalid_settings_root_raises_exact_message(self) -> None:
        self._patch_settings([])
        with self.assertRaises(ValueError) as ctx:
            Config.get_research_config()
        self.assertEqual(str(ctx.exception), "settings.yaml root must be a mapping")

    def test_invalid_research_section_raises_exact_message(self) -> None:
        self._patch_settings({"research": []})
        with self.assertRaises(ValueError) as ctx:
            Config.get_research_config()
        self.assertEqual(str(ctx.exception), "settings.research must be a mapping")

    def test_parser_value_error_propagates_unchanged(self) -> None:
        self._patch_settings(
            {"research": {"trusted_primary_domains": ["https://bad.example.com"]}}
        )
        with self.assertRaises(ValueError) as ctx:
            Config.get_research_config()
        # The parser's own message reaches the caller rebrand-free.
        self.assertIn("https://bad.example.com", str(ctx.exception))
        self.assertNotIn("settings.research", str(ctx.exception))
        self.assertNotIn("settings.yaml root", str(ctx.exception))

    def test_unknown_research_key_propagates_parser_error(self) -> None:
        self._patch_settings({"research": {"unknown_key": True}})
        with self.assertRaises(ValueError) as ctx:
            Config.get_research_config()
        self.assertIn("unknown_key", str(ctx.exception))


class TestStructuralBoundaries(unittest.TestCase):
    """AST guarantees on src/core/config.py (new method + untouched get_settings)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = CONFIG_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls._get_research_config = cls._find_function(cls.tree, "get_research_config")
        cls._get_settings = cls._find_function(cls.tree, "get_settings")

    @staticmethod
    def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
        raise AssertionError(f"function not found: {name}")

    @staticmethod
    def _code_text(node: ast.AST) -> str:
        """Unparsed function code with its docstring removed (the
        docstring may legitimately DOCUMENT these prohibitions)."""
        clone = ast.parse(ast.unparse(node))
        body = clone.body[0].body  # the function's body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        return ast.unparse(ast.Module(body=body, type_ignores=[]))

    def test_new_method_does_not_reference_research_execution(self) -> None:
        self.assertIsNotNone(self._get_research_config)
        body_text = self._code_text(self._get_research_config)
        for forbidden in (
            "Researcher",
            "HackerNewsAdapter",
            "GitHubAdapter",
            "OfficialRssAdapter",
            "run_live_research",
            "build_live_researcher",
            "SourceType",
        ):
            self.assertNotIn(forbidden, body_text)

    def test_new_method_only_uses_from_mapping_and_get_settings(self) -> None:
        body_text = ast.unparse(self._get_research_config)
        self.assertIn("cls.get_settings()", body_text)
        self.assertIn("LiveResearchConfig.from_mapping", body_text)

    def test_get_settings_implementation_not_altered_conceptually(self) -> None:
        self.assertIsNotNone(self._get_settings)
        body_text = ast.unparse(self._get_settings)
        self.assertIn("cls.SETTINGS_FILE", body_text)
        self.assertIn("yaml.safe_load", body_text)
        self.assertIn("_settings_cache", body_text)

    def test_module_imports_only_live_config_from_research(self) -> None:
        imported: set = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imported.add(f"{node.module}.{alias.name}")
        research_imports = {
            name for name in imported if name.startswith("src.research")
        }
        self.assertEqual(
            research_imports, {"src.research.live_config.LiveResearchConfig"}
        )


if __name__ == "__main__":
    unittest.main()
