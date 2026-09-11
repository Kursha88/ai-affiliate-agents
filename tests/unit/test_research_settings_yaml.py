"""Tests for the REAL research section in config/settings.yaml (Step 13D).

The only step that reads the real settings file. It verifies the YAML
parses, the new ``research`` section is well-formed, and the existing
``Config.get_research_config()`` loader parses it into the exact
expected ``LiveResearchConfig``. unittest only; NO network fetches,
no Researcher execution, no DB.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import Config  # noqa: E402
from src.research.adapters.rss import OfficialFeed  # noqa: E402
from src.research.live_config import LiveResearchConfig  # noqa: E402

SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"


class TestResearchSettingsYaml(unittest.TestCase):
    """Real-file verification of the research config section."""

    @classmethod
    def setUpClass(cls) -> None:
        # settings.yaml is text; parse with safe_load only.
        with SETTINGS_PATH.open("r", encoding="utf-8") as handle:
            cls.settings = yaml.safe_load(handle)

    def setUp(self) -> None:
        # Reset the settings cache so the loader reads the REAL file;
        # restore whatever was cached before the test ran.
        self._previous_cache = Config._settings_cache
        Config._settings_cache = None
        self.addCleanup(self._restore_cache)

    def _restore_cache(self) -> None:
        Config._settings_cache = self._previous_cache

    # ── 1-4. YAML shape ───────────────────────────────────────────────

    def test_settings_yaml_parses_with_safe_load(self) -> None:
        self.assertIsNotNone(self.settings)

    def test_yaml_root_is_a_dict(self) -> None:
        self.assertIsInstance(self.settings, dict)

    def test_top_level_research_exists(self) -> None:
        self.assertIn("research", self.settings)

    def test_research_is_a_dict(self) -> None:
        self.assertIsInstance(self.settings["research"], dict)

    # ── 5. real loader parses the real file ───────────────────────────

    def test_get_research_config_parses_real_settings(self) -> None:
        config = Config.get_research_config()
        self.assertIsInstance(config, LiveResearchConfig)

    # ── 6-12. exact parsed values ─────────────────────────────────────

    def test_trusted_primary_domains_exact(self) -> None:
        config = Config.get_research_config()
        self.assertEqual(config.trusted_primary_domains, ("github.blog",))

    def test_blog_feeds_length_is_one(self) -> None:
        config = Config.get_research_config()
        self.assertEqual(len(config.blog_feeds), 1)

    def test_blog_feed_values_exact(self) -> None:
        config = Config.get_research_config()
        feed = config.blog_feeds[0]
        self.assertIsInstance(feed, OfficialFeed)
        self.assertEqual(feed.name, "GitHub Blog")
        self.assertEqual(feed.feed_url, "https://github.blog/feed/")
        self.assertEqual(feed.trusted_domain, "github.blog")

    def test_docs_feeds_length_is_one(self) -> None:
        config = Config.get_research_config()
        self.assertEqual(len(config.docs_feeds), 1)

    def test_docs_feed_values_exact(self) -> None:
        config = Config.get_research_config()
        feed = config.docs_feeds[0]
        self.assertIsInstance(feed, OfficialFeed)
        self.assertEqual(feed.name, "GitHub Changelog")
        self.assertEqual(feed.feed_url, "https://github.blog/changelog/feed/")
        self.assertEqual(feed.trusted_domain, "github.blog")

    def test_live_kwargs_contains_exactly_three_keys(self) -> None:
        config = Config.get_research_config()
        kwargs = config.live_kwargs()
        self.assertEqual(
            set(kwargs.keys()),
            {"blog_feeds", "docs_feeds", "trusted_primary_domains"},
        )

    def test_no_duplicate_trusted_domains_after_parsing(self) -> None:
        config = Config.get_research_config()
        domains = config.trusted_primary_domains
        self.assertEqual(len(domains), len(set(domains)))
        # The feed-level trusted_domain is part of the same curated set.
        feed_domains = [feed.trusted_domain for feed in config.blog_feeds] + [
            feed.trusted_domain for feed in config.docs_feeds
        ]
        self.assertEqual(set(feed_domains), set(domains))

    # ── 13. no network ────────────────────────────────────────────────

    def test_no_http_or_network_in_test_file(self) -> None:
        # AST-based scan: no network modules imported and no network
        # calls made anywhere in this test file. Immune to literals
        # and docstrings (unlike raw text matching).
        import ast

        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        imported: set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for module in imported:
            top = module.split(".")[0]
            self.assertFalse(
                top in {"requests", "urllib", "http", "socket", "httpx", "aiohttp"},
                f"network import: {module}",
            )
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    root = getattr(func.value, "id", "")
                elif isinstance(func, ast.Name):
                    root = func.id
                else:
                    root = ""
                self.assertNotIn(
                    root, {"requests", "urlopen", "socket", "httpx", "aiohttp"}
                )


if __name__ == "__main__":
    unittest.main()
