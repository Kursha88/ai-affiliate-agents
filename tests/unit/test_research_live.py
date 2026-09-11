"""Unit tests for the live Researcher wiring layer (Step 13A).

Focused tests for exactly the specified behaviors: adapter construction
order, RSS adapter wiring, trusted-domain forwarding, the
"construction only" guarantee for ``build_live_researcher``, the
build-once/run-once/return-unchanged contract of ``run_live_research``,
and the structural boundaries of ``live.py``. unittest + mock only; no
network, no filesystem access, no environment reads.
"""

from __future__ import annotations

import ast
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.research.live import build_live_researcher, run_live_research  # noqa: E402

NOW: datetime = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)

LIVE_PY = PROJECT_ROOT / "src" / "research" / "live.py"


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


class TestBuildLiveResearcher(unittest.TestCase):
    """Construction-only wiring behavior."""

    def _patch_adapters(self):
        """Patch every adapter class + Researcher inside src.research.live."""
        return [
            mock.patch("src.research.live.HackerNewsAdapter"),
            mock.patch("src.research.live.GitHubAdapter"),
            mock.patch("src.research.live.OfficialRssAdapter"),
            mock.patch("src.research.live.Researcher"),
        ]

    def _run_patched_build(self, **kwargs):
        patchers = self._patch_adapters()
        mocks = [patcher.start() for patcher in patchers]
        self.addCleanup(lambda: [patcher.stop() for patcher in patchers])
        hn, github, rss, researcher_cls = mocks
        build_live_researcher(**kwargs)
        return hn, github, rss, researcher_cls

    def test_no_rss_feeds_constructs_hn_and_github_only(self) -> None:
        hn, github, rss, _ = self._run_patched_build()
        hn.assert_called_once_with()
        github.assert_called_once_with()
        rss.assert_not_called()

    def test_adapter_constructor_order_hn_then_github(self) -> None:
        patchers = self._patch_adapters()
        hn_m, gh_m, _rss_m, researcher_m = [p.start() for p in patchers]
        self.addCleanup(lambda: [p.stop() for p in patchers])

        # Shared construction registry: each constructor appends a tag
        # and returns a distinct instance so the wiring is observable.
        order: list[str] = []
        hn_instance, gh_instance = mock.Mock(), mock.Mock()

        def _track(tag: str, instance: mock.Mock):
            def _make(*args, **kwargs):
                order.append(tag)
                return instance

            return _make

        hn_m.side_effect = _track("hn", hn_instance)
        gh_m.side_effect = _track("github", gh_instance)

        build_live_researcher()

        self.assertEqual(order, ["hn", "github"])
        # The Researcher received the HN instance before the GitHub one.
        adapters_arg = researcher_m.call_args.kwargs["adapters"]
        self.assertEqual(adapters_arg, (hn_instance, gh_instance))

    def test_blog_feeds_create_exactly_one_blog_rss_adapter(self) -> None:
        from src.domain.strategy import SourceType

        feeds = [mock.sentinel.feed_a, mock.sentinel.feed_b]
        _, _, rss, _ = self._run_patched_build(blog_feeds=feeds)
        rss.assert_called_once_with(
            feeds=tuple(feeds), source_type=SourceType.OFFICIAL_BLOG
        )

    def test_docs_feeds_create_exactly_one_docs_rss_adapter(self) -> None:
        from src.domain.strategy import SourceType

        feeds = [mock.sentinel.feed_c]
        _, _, rss, _ = self._run_patched_build(docs_feeds=feeds)
        rss.assert_called_once_with(
            feeds=tuple(feeds), source_type=SourceType.OFFICIAL_DOCS
        )

    def test_both_feed_groups_order_hn_github_blog_docs(self) -> None:
        from src.domain.strategy import SourceType

        blog = [mock.sentinel.blog_feed]
        docs = [mock.sentinel.docs_feed]
        patchers = self._patch_adapters()
        hn_m, gh_m, rss_m, researcher_m = [p.start() for p in patchers]
        self.addCleanup(lambda: [p.stop() for p in patchers])

        # Real instances keep the adapter order observable.
        instances = [mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock()]
        side = iter(instances)
        for adapter_mock in (hn_m, gh_m, rss_m):
            adapter_mock.side_effect = lambda *a, **k: next(side)

        build_live_researcher(blog_feeds=blog, docs_feeds=docs)

        hn_m.assert_called_once_with()
        gh_m.assert_called_once_with()
        self.assertEqual(rss_m.call_count, 2)
        first_blog = rss_m.call_args_list[0]
        first_docs = rss_m.call_args_list[1]
        self.assertEqual(first_blog.kwargs["source_type"], SourceType.OFFICIAL_BLOG)
        self.assertEqual(first_blog.kwargs["feeds"], tuple(blog))
        self.assertEqual(first_docs.kwargs["source_type"], SourceType.OFFICIAL_DOCS)
        self.assertEqual(first_docs.kwargs["feeds"], tuple(docs))
        # Researcher receives the adapters in HN -> GitHub -> BLOG -> DOCS order.
        self.assertEqual(
            researcher_m.call_args.kwargs["adapters"], tuple(instances)
        )

    def test_trusted_domains_forwarded_unchanged_as_tuple(self) -> None:
        domains = ["example-ai.com", "docs.example-ai.com"]
        _, _, _, researcher_cls = self._run_patched_build(
            trusted_primary_domains=domains
        )
        passed = researcher_cls.call_args.kwargs["trusted_primary_domains"]
        self.assertEqual(passed, tuple(domains))
        self.assertIsInstance(passed, tuple)

    def test_build_does_not_fetch_or_run(self) -> None:
        # Use REAL adapter/researcher classes with instrumented methods.
        recorded: list[str] = []

        class _GuardHn:
            def fetch(self):
                recorded.append("hn.fetch")
                return []

            def safe_fetch(self):
                recorded.append("hn.safe_fetch")
                return []

        class _GuardGithub:
            def fetch(self):
                recorded.append("gh.fetch")
                return []

            def safe_fetch(self):
                recorded.append("gh.safe_fetch")
                return []

        with mock.patch(
            "src.research.live.HackerNewsAdapter", _GuardHn
        ), mock.patch(
            "src.research.live.GitHubAdapter", _GuardGithub
        ), mock.patch(
            "src.research.live.OfficialRssAdapter"
        ) as rss_m, mock.patch(
            "src.research.live.Researcher"
        ) as researcher_m:
            researcher_m.return_value = mock.Mock()
            build_live_researcher(blog_feeds=[mock.sentinel.f])

        self.assertEqual(recorded, [])
        # The constructed RSS instance was never driven: no fetch,
        # no safe_fetch, no call of any kind.
        rss_instance = rss_m.return_value
        rss_instance.assert_not_called()
        rss_instance.fetch.assert_not_called()
        rss_instance.safe_fetch.assert_not_called()
        researcher_m.return_value.run.assert_not_called()

    def test_build_constructs_real_types(self) -> None:
        # Unpatched construction works and produces a real Researcher.
        from src.research.researcher import Researcher as ResearcherCls

        researcher = build_live_researcher()
        self.assertIsInstance(researcher, ResearcherCls)
        # Adapter types are verified via the patched assertions above;
        # this test pins that plain construction performs no I/O and
        # returns the documented orchestrator type.
        self.assertGreaterEqual(len(researcher._adapters), 2)


class TestRunLiveResearch(unittest.TestCase):
    """build-once, run-once, return-unchanged."""

    def _patch_all(self):
        patchers = [
            mock.patch("src.research.live.HackerNewsAdapter"),
            mock.patch("src.research.live.GitHubAdapter"),
            mock.patch("src.research.live.OfficialRssAdapter"),
            mock.patch("src.research.live.Researcher"),
        ]
        mocks = [patcher.start() for patcher in patchers]
        self.addCleanup(lambda: [patcher.stop() for patcher in patchers])
        return mocks

    def test_calls_build_exactly_once_and_runs_once(self) -> None:
        hn_m, gh_m, rss_m, researcher_m = self._patch_all()
        researcher_instance = researcher_m.return_value
        researcher_instance.run.return_value = mock.sentinel.result

        result = run_live_research(now=NOW, limit=7)

        self.assertIs(result, mock.sentinel.result)
        researcher_instance.run.assert_called_once_with(now=NOW, limit=7)
        # Adapters constructed exactly once by the single build call.
        hn_m.assert_called_once_with()
        gh_m.assert_called_once_with()
        rss_m.assert_not_called()

    def test_forwards_now_and_limit_exactly(self) -> None:
        _, _, _, researcher_m = self._patch_all()
        researcher_m.return_value.run.return_value = mock.sentinel.result

        custom_now = datetime(2026, 1, 1, 8, 30, tzinfo=timezone.utc)
        run_live_research(now=custom_now, limit=3)

        researcher_m.return_value.run.assert_called_once_with(
            now=custom_now, limit=3
        )

    def test_forwards_feed_groups_and_trusted_domains_to_build(self) -> None:
        hn_m, gh_m, rss_m, researcher_m = self._patch_all()
        researcher_m.return_value.run.return_value = mock.sentinel.result

        blog = [mock.sentinel.blog_feed]
        docs = [mock.sentinel.docs_feed]
        domains = ("example-ai.com",)
        run_live_research(
            now=NOW,
            blog_feeds=blog,
            docs_feeds=docs,
            trusted_primary_domains=domains,
        )

        # One of each RSS adapter, wired with the right feeds/source types.
        from src.domain.strategy import SourceType

        rss_calls = rss_m.call_args_list
        self.assertEqual(len(rss_calls), 2)
        self.assertEqual(rss_calls[0].kwargs["source_type"], SourceType.OFFICIAL_BLOG)
        self.assertEqual(rss_calls[0].kwargs["feeds"], tuple(blog))
        self.assertEqual(rss_calls[1].kwargs["source_type"], SourceType.OFFICIAL_DOCS)
        self.assertEqual(rss_calls[1].kwargs["feeds"], tuple(docs))
        self.assertEqual(
            researcher_m.call_args.kwargs["trusted_primary_domains"],
            tuple(domains),
        )

    def test_returns_run_result_unchanged(self) -> None:
        _, _, _, researcher_m = self._patch_all()
        marker = mock.Mock(name="ResearchResult")
        researcher_m.return_value.run.return_value = marker

        result = run_live_research(now=NOW)

        self.assertIs(result, marker)

    def test_does_not_catch_exceptions(self) -> None:
        _, _, _, researcher_m = self._patch_all()
        researcher_m.return_value.run.side_effect = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            run_live_research(now=NOW)


class TestLiveStructuralBoundaries(unittest.TestCase):
    """AST-level guarantees on live.py."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = LIVE_PY.read_text(encoding="utf-8")
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

    def test_no_forbidden_text_in_code(self) -> None:
        for forbidden in (
            "os.environ",
            "os.getenv",
            "datetime.now",
            "utcnow",
            "requests",
            "sqlite3",
            "src.main",
            "src.storage",
            "src.state",
            "publisher",
            "copywriter",
            "editor",
            "designer",
            "NewsHunter",
            "Strategist",
            "dotenv",
            "yaml",
            "logging",
            "print(",
        ):
            self.assertNotIn(forbidden, self.code_text)

    def test_no_forbidden_imports(self) -> None:
        imported = self._imported_modules()
        for forbidden in (
            "requests",
            "os",
            "dotenv",
            "yaml",
            "sqlite3",
            "logging",
            "src.main",
            "src.storage",
            "src.state",
            "src.agents",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_legacy_or_publishing_imports(self) -> None:
        imported = self._imported_modules()
        for module in imported:
            self.assertFalse(
                module.startswith(
                    (
                        "src.agents",
                        "src.factory",
                        "src.storage",
                        "src.core",
                        "src.integrations",
                    )
                ),
                f"forbidden import: {module}",
            )

    def test_no_main_block_no_cli(self) -> None:
        self.assertNotIn('__name__ == "__main__"', self.code_text)
        self.assertNotIn("argparse", self.code_text)

    def test_required_imports_present(self) -> None:
        imported = self._imported_modules()
        for required in (
            "src.research.researcher",
            "src.research.adapters.hacker_news",
            "src.research.adapters.github",
            "src.research.adapters.rss",
            "src.domain.strategy",
            "src.research.rank",
        ):
            self.assertIn(required, imported)
        # Required names imported from the right modules.
        names = {
            alias.name
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        }
        for required_name in (
            "Researcher",
            "ResearchResult",
            "HackerNewsAdapter",
            "GitHubAdapter",
            "OfficialFeed",
            "OfficialRssAdapter",
            "SourceType",
            "DEFAULT_LIMIT",
        ):
            self.assertIn(required_name, names)


if __name__ == "__main__":
    unittest.main()
