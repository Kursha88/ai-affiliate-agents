"""Unit tests for the pure research config model (Step 13B).

Focused tests for exactly the specified behaviors: defaults, trusted-
domain normalization/rejection, feed parsing/delegation, top-level
validation, ``live_kwargs`` semantics, immutability, and the structural
purity of ``live_config.py``. unittest only; no network, no filesystem
access, no environment reads.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.research.adapters.rss import OfficialFeed  # noqa: E402
from src.research.live_config import LiveResearchConfig  # noqa: E402

LIVE_CONFIG_PY = PROJECT_ROOT / "src" / "research" / "live_config.py"

VALID_BLOG_FEED = {
    "name": "Example Blog",
    "feed_url": "https://example.com/feed.xml",
    "trusted_domain": "example.com",
}
VALID_DOCS_FEED = {
    "name": "Example Docs",
    "feed_url": "https://docs.example.com/feed.xml",
    "trusted_domain": "docs.example.com",
}


def _strip_docstrings(tree: ast.AST) -> str:
    """Source text with docstrings removed (code-only text scans)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


class TestDefaultsAndValidParsing(unittest.TestCase):
    """Spec cases 1, 2, 14, 15, 16."""

    def test_empty_mapping_yields_all_empty_tuples(self) -> None:
        config = LiveResearchConfig.from_mapping({})
        self.assertEqual(config.blog_feeds, ())
        self.assertEqual(config.docs_feeds, ())
        self.assertEqual(config.trusted_primary_domains, ())

    def test_valid_trusted_domains_parsed(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {"trusted_primary_domains": ["example.com", "docs.example.com"]}
        )
        self.assertEqual(
            config.trusted_primary_domains, ("example.com", "docs.example.com")
        )

    def test_valid_blog_feed_becomes_official_feed(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {"official_blog_feeds": [VALID_BLOG_FEED]}
        )
        self.assertEqual(len(config.blog_feeds), 1)
        feed = config.blog_feeds[0]
        self.assertIsInstance(feed, OfficialFeed)
        self.assertEqual(feed.name, "Example Blog")
        self.assertEqual(feed.feed_url, "https://example.com/feed.xml")
        self.assertEqual(feed.trusted_domain, "example.com")

    def test_valid_docs_feed_becomes_official_feed(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {"official_docs_feeds": [VALID_DOCS_FEED]}
        )
        self.assertEqual(len(config.docs_feeds), 1)
        feed = config.docs_feeds[0]
        self.assertIsInstance(feed, OfficialFeed)
        self.assertEqual(feed.trusted_domain, "docs.example.com")

    def test_multiple_feeds_preserve_order(self) -> None:
        second = {
            "name": "Second Blog",
            "feed_url": "https://second.example.org/rss",
            "trusted_domain": "second.example.org",
        }
        config = LiveResearchConfig.from_mapping(
            {"official_blog_feeds": [VALID_BLOG_FEED, second]}
        )
        self.assertEqual(
            [feed.name for feed in config.blog_feeds], ["Example Blog", "Second Blog"]
        )


class TestTrustedDomainNormalization(unittest.TestCase):
    """Spec cases 3-6."""

    def test_whitespace_and_lowercase_normalized(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {"trusted_primary_domains": ["  OpenAI.COM  "]}
        )
        self.assertEqual(config.trusted_primary_domains, ("openai.com",))

    def test_leading_www_removed(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {"trusted_primary_domains": ["www.example.com"]}
        )
        self.assertEqual(config.trusted_primary_domains, ("example.com",))

    def test_normalized_duplicates_removed(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {
                "trusted_primary_domains": [
                    "Example.com",
                    "www.example.com",
                    "docs.example.com",
                ]
            }
        )
        self.assertEqual(
            config.trusted_primary_domains, ("example.com", "docs.example.com")
        )

    def test_first_occurrence_order_preserved(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {
                "trusted_primary_domains": [
                    "zeta.example.net",
                    "alpha.example.net",
                ]
            }
        )
        self.assertEqual(
            config.trusted_primary_domains,
            ("zeta.example.net", "alpha.example.net"),
        )


class TestTrustedDomainRejection(unittest.TestCase):
    """Spec cases 7-13."""

    def _assert_rejected(self, domains) -> None:
        with self.assertRaises(ValueError):
            LiveResearchConfig.from_mapping({"trusted_primary_domains": domains})

    def test_blank_trusted_domain_rejected(self) -> None:
        self._assert_rejected(["   "])

    def test_scheme_domain_rejected(self) -> None:
        self._assert_rejected(["https://example.com"])

    def test_path_domain_rejected(self) -> None:
        self._assert_rejected(["example.com/path"])

    def test_port_domain_rejected(self) -> None:
        self._assert_rejected(["example.com:443"])

    def test_query_fragment_and_credentials_rejected(self) -> None:
        self._assert_rejected(["example.com?x=1"])
        self._assert_rejected(["example.com#frag"])
        self._assert_rejected(["user@example.com"])

    def test_non_dotted_domain_rejected(self) -> None:
        self._assert_rejected(["localhost"])

    def test_trusted_domains_string_instead_of_list_rejected(self) -> None:
        self._assert_rejected("example.com")

    def test_trusted_domain_non_string_item_rejected(self) -> None:
        self._assert_rejected(["example.com", 42])


class TestFeedParsing(unittest.TestCase):
    """Spec cases 17-24."""

    def test_duplicate_feed_configs_preserved(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {"official_blog_feeds": [VALID_BLOG_FEED, dict(VALID_BLOG_FEED)]}
        )
        self.assertEqual(len(config.blog_feeds), 2)
        self.assertEqual(
            [feed.feed_url for feed in config.blog_feeds],
            [VALID_BLOG_FEED["feed_url"], VALID_BLOG_FEED["feed_url"]],
        )

    def test_feed_list_as_string_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LiveResearchConfig.from_mapping(
                {"official_blog_feeds": "https://example.com/feed.xml"}
            )

    def test_feed_entry_non_mapping_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LiveResearchConfig.from_mapping(
                {"official_blog_feeds": ["https://example.com/feed.xml"]}
            )

    def test_missing_feed_name_rejected(self) -> None:
        broken = {
            "feed_url": "https://example.com/feed.xml",
            "trusted_domain": "example.com",
        }
        with self.assertRaises(ValueError):
            LiveResearchConfig.from_mapping({"official_blog_feeds": [broken]})

    def test_missing_feed_url_rejected(self) -> None:
        broken = {"name": "Example Blog", "trusted_domain": "example.com"}
        with self.assertRaises(ValueError):
            LiveResearchConfig.from_mapping({"official_blog_feeds": [broken]})

    def test_missing_trusted_domain_rejected(self) -> None:
        broken = {"name": "Example Blog", "feed_url": "https://example.com/feed.xml"}
        with self.assertRaises(ValueError):
            LiveResearchConfig.from_mapping({"official_blog_feeds": [broken]})

    def test_unknown_feed_key_rejected(self) -> None:
        broken = {**VALID_BLOG_FEED, "platform": "telegram"}
        with self.assertRaises(ValueError):
            LiveResearchConfig.from_mapping({"official_blog_feeds": [broken]})

    def test_official_feed_validation_error_propagates_unchanged(self) -> None:
        # OfficialFeed's own ValueError (invalid feed_url scheme here)
        # must reach the caller rebranded-free: same type, same message.
        broken = {
            "name": "Example Blog",
            "feed_url": "ftp://example.com/feed.xml",
            "trusted_domain": "example.com",
        }
        with self.assertRaises(ValueError) as ctx:
            LiveResearchConfig.from_mapping({"official_blog_feeds": [broken]})
        self.assertIn("OfficialFeed.feed_url", str(ctx.exception))

    def test_docs_feed_official_feed_error_propagates(self) -> None:
        broken = {
            "name": "Example Docs",
            "feed_url": "https://docs.example.com/feed.xml",
            "trusted_domain": "https://docs.example.com",
        }
        with self.assertRaises(ValueError):
            LiveResearchConfig.from_mapping({"official_docs_feeds": [broken]})


class TestTopLevelValidation(unittest.TestCase):
    """Spec cases 25, 26."""

    def test_unknown_top_level_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LiveResearchConfig.from_mapping({"foo": 1})

    def test_non_mapping_data_rejected(self) -> None:
        for bad in ("research", ["example.com"], 42, None, ("a",)):
            with self.assertRaises(ValueError):
                LiveResearchConfig.from_mapping(bad)


class TestLiveKwargs(unittest.TestCase):
    """Spec cases 27-29."""

    def test_live_kwargs_returns_exact_three_keys(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {
                "trusted_primary_domains": ["example.com"],
                "official_blog_feeds": [VALID_BLOG_FEED],
            }
        )
        kwargs = config.live_kwargs()
        self.assertEqual(
            set(kwargs.keys()),
            {"blog_feeds", "docs_feeds", "trusted_primary_domains"},
        )

    def test_live_kwargs_values_equal_config_tuples(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {
                "trusted_primary_domains": ["example.com"],
                "official_blog_feeds": [VALID_BLOG_FEED],
                "official_docs_feeds": [VALID_DOCS_FEED],
            }
        )
        kwargs = config.live_kwargs()
        self.assertEqual(kwargs["blog_feeds"], config.blog_feeds)
        self.assertEqual(kwargs["docs_feeds"], config.docs_feeds)
        self.assertEqual(
            kwargs["trusted_primary_domains"], config.trusted_primary_domains
        )

    def test_live_kwargs_returns_new_dict_each_call(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {"trusted_primary_domains": ["example.com"]}
        )
        first = config.live_kwargs()
        second = config.live_kwargs()
        self.assertIsNot(first, second)
        self.assertEqual(first, second)
        first["blog_feeds"] = ()  # mutating one must not affect the other
        self.assertEqual(second["blog_feeds"], config.blog_feeds)


class TestImmutability(unittest.TestCase):
    """Spec case 30."""

    def test_dataclass_is_frozen(self) -> None:
        config = LiveResearchConfig.from_mapping(
            {"trusted_primary_domains": ["example.com"]}
        )
        with self.assertRaises(Exception):
            config.trusted_primary_domains = ()  # type: ignore[misc]


class TestStructuralBoundaries(unittest.TestCase):
    """Spec case 31."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = LIVE_CONFIG_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.code_text = _strip_docstrings(cls.tree)

    def _imported_modules(self) -> set:
        imported: set = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        return imported

    def test_no_forbidden_imports(self) -> None:
        imported = self._imported_modules()
        for forbidden in (
            "requests",
            "yaml",
            "os",
            "dotenv",
            "sqlite3",
            "socket",
            "logging",
            "src.main",
            "src.research.live",
            "src.research.researcher",
            "src.research.adapters.hacker_news",
            "src.research.adapters.github",
            "src.domain.strategy",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_forbidden_names_in_code(self) -> None:
        for forbidden in (
            "os.environ",
            "os.getenv",
            "datetime.now",
            "utcnow",
            "yaml",
            "sqlite3",
            "print(",
            "logging.",
            "build_live_researcher",
            "run_live_research",
            "Researcher",
            "SourceType",
            "HackerNewsAdapter",
            "GitHubAdapter",
            "requests",
        ):
            self.assertNotIn(forbidden, self.code_text)

    def test_no_open_or_network_calls(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    self.assertNotIn(
                        func.id, {"open", "urlopen", "socket", "connect"}
                    )
                elif isinstance(func, ast.Attribute):
                    root = func.value
                    root_name = getattr(root, "id", "")
                    # Mapping.get / dict.get are legitimate; network roots
                    # (requests, urllib, socket) are not.
                    self.assertNotIn(
                        root_name, {"requests", "urllib", "urllib3", "socket", "http"}
                    )
                    self.assertNotIn(func.attr, {"urlopen", "open"})


if __name__ == "__main__":
    unittest.main()
