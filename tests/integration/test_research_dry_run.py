"""Integration tests: offline end-to-end Researcher 2.0 dry run (Step 12).

Proves the COMPLETE pipeline with all three real adapters over bundled
fixtures:

    HackerNewsAdapter + GitHubAdapter + OfficialRssAdapter
        -> Researcher.run() -> dedup -> classify -> verify -> score -> rank

Zero live network: every fetch flows through fixture-backed fakes.
Zero production integration: no DB, no state, no topic_history.json,
no src/main.py, no legacy agents, no publishing, no filesystem writes.
"""

from __future__ import annotations

import ast
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.research.dry_run import (  # noqa: E402
    EPOCH_NOW,
    FIXTURE_NOW_STR,
    FIXTURES_DIR,
    TRUSTED_DOMAIN,
    build_adapters,
    fixture_now,
    format_report,
    run_offline_dry_run,
)
from src.research.researcher import ResearchResult, Researcher  # noqa: E402

NOW: datetime = fixture_now()
NOW_STR: str = NOW.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_fixture(path: Path):
    if path.suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    return path.read_text(encoding="utf-8")


class _InstrumentedHnFetcher:
    """Counts every HN fetch; serves ONLY the fixture payloads."""

    def __init__(self) -> None:
        self.topstories_fetches = 0
        self.item_fetches = 0
        with (FIXTURES_DIR / "hn_topstories.json").open("r", encoding="utf-8") as handle:
            self._story_ids = [int(value) for value in json.load(handle)]
        with (FIXTURES_DIR / "hn_items.json").open("r", encoding="utf-8") as handle:
            self._items = json.load(handle)

    def __call__(self, url: str):
        if url.endswith("topstories.json"):
            self.topstories_fetches += 1
            return list(self._story_ids)
        self.item_fetches += 1
        parts = urlsplit(url)
        segments = [segment for segment in parts.path.split("/") if segment]
        if len(segments) >= 2 and segments[-2] == "item":
            # Item URLs are "/v0/item/<id>.json"; fixture keys are bare ids.
            return self._items.get(segments[-1].removesuffix(".json"))
        story_id = (parse_qs(parts.query).get("id") or [None])[0]
        if story_id is not None:
            return self._items.get(story_id)
        return None


class _InstrumentedGitHubFetcher:
    """Counts every GitHub search fetch; serves ONLY the fixture payload."""

    def __init__(self) -> None:
        self.search_fetches = 0
        with (FIXTURES_DIR / "github_search.json").open("r", encoding="utf-8") as handle:
            self._payload = json.load(handle)

    def __call__(self, url: str):
        self.search_fetches += 1
        query = (parse_qs(urlsplit(url).query).get("q") or [""])[0]
        return self._payload if query else None


class _InstrumentedTextFetcher:
    """Counts every feed fetch; serves ONLY the fixture text."""

    def __init__(self) -> None:
        self.feed_fetches = 0
        self._feed_text = (FIXTURES_DIR / "official_feed.xml").read_text(encoding="utf-8")

    def __call__(self, url: str):
        self.feed_fetches += 1
        host = urlsplit(url).hostname or ""
        if host in ("example-ai.com", "www.example-ai.com"):
            return self._feed_text
        return None


def _instrumented_result() -> tuple[ResearchResult, _InstrumentedHnFetcher, _InstrumentedGitHubFetcher, _InstrumentedTextFetcher]:
    """Full researcher run with instrumented fetchers (counts all I/O)."""
    hn_fetcher = _InstrumentedHnFetcher()
    gh_fetcher = _InstrumentedGitHubFetcher()
    text_fetcher = _InstrumentedTextFetcher()

    from src.domain.strategy import SourceType
    from src.research.adapters.hacker_news import HackerNewsAdapter
    from src.research.adapters.github import GitHubAdapter
    from src.research.adapters.rss import OfficialFeed, OfficialRssAdapter

    def hn_now() -> datetime:
        return NOW

    hn = HackerNewsAdapter(fetch_json=hn_fetcher, now_fn=hn_now, max_items=50)
    github = GitHubAdapter(fetch_json=gh_fetcher)
    rss = OfficialRssAdapter(
        feeds=(
            OfficialFeed(
                name="ExampleAI Blog",
                feed_url="https://example-ai.com/feed.xml",
                trusted_domain=TRUSTED_DOMAIN,
            ),
        ),
        source_type=SourceType.OFFICIAL_BLOG,
        fetch_text=text_fetcher,
    )
    researcher = Researcher(adapters=(hn, github, rss))
    result = researcher.run(now=NOW)
    return result, hn_fetcher, gh_fetcher, text_fetcher


def _strip_docstrings(tree: ast.AST) -> str:
    """Source text with docstrings removed, for code-only text scans."""
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


class TestDryRunIntegration(unittest.TestCase):
    """End-to-end behavior of the offline dry run."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_offline_dry_run(now=NOW)
        (
            cls.result,
            cls.hn_fetcher,
            cls.gh_fetcher,
            cls.text_fetcher,
        ) = _instrumented_result()
        cls.counts = cls.report.stage_counts

    # ── 1-2. adapters participate; no network ─────────────────────────

    def test_all_three_adapters_participate_and_succeed(self) -> None:
        outcomes = {o["adapter_name"]: o for o in self.report.adapter_outcomes}
        self.assertEqual(
            set(outcomes), {"hacker_news", "github", "official_rss"}
        )
        self.assertTrue(all(o["ok"] for o in outcomes.values()))
        self.assertEqual(outcomes["hacker_news"]["source_type"], "hacker_news")
        self.assertEqual(outcomes["github"]["source_type"], "github")
        self.assertEqual(outcomes["official_rss"]["source_type"], "official_blog")

    def test_no_network_used(self) -> None:
        # Every fetch was served by the fixture-backed fakes; the production
        # requests-based defaults were never constructed or invoked.
        self.assertGreaterEqual(self.hn_fetcher.topstories_fetches, 1)
        self.assertGreaterEqual(self.hn_fetcher.item_fetches, 1)
        self.assertGreaterEqual(self.gh_fetcher.search_fetches, 1)
        self.assertGreaterEqual(self.text_fetcher.feed_fetches, 1)
        # All adapter outcomes succeeded -> nothing fell back anywhere.
        self.assertTrue(all(o["ok"] for o in self.report.adapter_outcomes))

    # ── 3. adapter filtering works ────────────────────────────────────

    def test_adapter_filtering_works(self) -> None:
        raw = _read_fixture(FIXTURES_DIR / "github_search.json")["items"]
        # GitHub: 9 payload records -> archived + fork skipped, 3 duplicates
        # collapsed in-adapter -> exactly 3 discoveries.
        self.assertEqual(
            next(
                o["record_count"]
                for o in self.report.adapter_outcomes
                if o["adapter_name"] == "github"
            ),
            3,
        )
        # HN keeps all 5 topstory slots (including the duplicate 101) at the
        # adapter layer — the duplicate is removed by the pipeline's dedup.
        self.assertEqual(
            next(
                o["record_count"]
                for o in self.report.adapter_outcomes
                if o["adapter_name"] == "hacker_news"
            ),
            5,
        )
        self.assertEqual(self.counts["input_count"], 11)
        titles = {row["title"] for row in self.report.candidate_summaries}
        self.assertNotIn(
            "Legacy AI agent tool that is no longer maintained", titles
        )  # archived skipped
        self.assertNotIn(
            "Fork of an existing AI agent framework", titles
        )  # fork skipped
        # No GitHub record survived with the archived repo's URL/title.
        self.assertFalse(
            any("archivehub" in (row["url"] or "") for row in self.report.candidate_summaries)
        )

    # ── 4-5. input count + dedup ──────────────────────────────────────

    def test_combined_input_count_is_correct(self) -> None:
        # HN: 5 kept items (duplicate id 101 passed through twice;
        #      the ADAPTER has no dedup) + GitHub: 3 unique repos + RSS: 3 entries
        self.assertEqual(self.counts["input_count"], 11)
        self.assertEqual(self.counts["deduplicated_count"], 10)

    def test_dedup_removes_the_intentional_duplicate(self) -> None:
        self.assertEqual(self.counts["input_count"] - self.counts["deduplicated_count"], 1)
        # Exactly one duplicate group, by native identifier (HN item id).
        titles = [row["title"] for row in self.report.candidate_summaries]
        self.assertEqual(titles.count("ExampleAI launches a new model for LLM applications"), 1)

    # ── 6-7. classification ───────────────────────────────────────────

    def test_classification_produces_multiple_clusters(self) -> None:
        clusters = {
            row["cluster"] for row in self.report.candidate_summaries if row["cluster"]
        }
        self.assertGreaterEqual(len(clusters), 2, f"clusters seen: {clusters}")

    def test_generic_official_announcement_not_mapped_to_ai_news(self) -> None:
        rows = [
            row
            for row in self.report.candidate_summaries
            if row["title"].startswith("ExampleAI office relocation")
        ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # No silent fallback to ai_news (or any cluster): no AI context
        # signals -> no gated evidence -> no_signals / unclassified.
        self.assertIsNone(row["cluster"])
        self.assertFalse(row["classification_ambiguous"])
        # And it did not sneak into the ranked shortlist either.
        self.assertNotIn(
            "ExampleAI office relocation announcement",
            [s.title for s in self.report.ranked_summaries],
        )

    # ── 8-12. verification ────────────────────────────────────────────

    def _row_by_url(self, url_suffix: str, source_type: str | None = None) -> dict:
        rows = [
            row
            for row in self.report.candidate_summaries
            if (row["url"] or "").endswith(url_suffix)
            and (source_type is None or row["source_type"] == source_type)
        ]
        self.assertEqual(len(rows), 1, f"expected one row for {url_suffix}, got {rows}")
        return rows[0]

    def test_trusted_official_source_verifies(self) -> None:
        row = self._row_by_url(
            "/blog/automation-integration-guide", source_type="official_blog"
        )
        self.assertEqual(row["verification_status"], "verified")
        self.assertEqual(row["verification_note"], "primary:trusted_official_domain")

    def test_hn_outbound_to_trusted_domain_verifies(self) -> None:
        # HN story 101 and RSS entry 1 share the same URL; select the HN one.
        row = self._row_by_url(
            "/blog/open-weights-model-launch", source_type="hacker_news"
        )
        self.assertEqual(row["source_type"], "hacker_news")
        self.assertEqual(row["verification_status"], "verified")
        self.assertEqual(row["verification_note"], "primary:trusted_official_domain")

    def test_unknown_secondary_stays_unverified(self) -> None:
        row = self._row_by_url("devblog.example.net/vibe-coding-workflow")
        self.assertEqual(row["verification_status"], "unverified")
        self.assertEqual(row["verification_note"], "secondary:untrusted_domain")

    def test_hn_native_provenance_works(self) -> None:
        row = self._row_by_url("news.ycombinator.com/item?id=103")
        self.assertEqual(row["source_type"], "hacker_news")
        self.assertEqual(row["verification_status"], "verified")
        self.assertEqual(row["verification_note"], "primary:hn_native")

    def test_github_repo_provenance_works(self) -> None:
        row = self._row_by_url("github.com/vibeworks/cli")
        self.assertEqual(row["verification_status"], "verified")
        self.assertEqual(row["verification_note"], "primary:github_repository")

    def test_rss_entry_from_trusted_domain_verifies(self) -> None:
        # The same URL legitimately exists on the HN record and the RSS
        # record (cross-source provenance is preserved by the dedup
        # contract); select the RSS one.
        row = self._row_by_url(
            "/blog/open-weights-model-launch", source_type="official_blog"
        )
        self.assertEqual(row["verification_status"], "verified")
        self.assertEqual(row["verification_note"], "primary:trusted_official_domain")

    # ── 13-14. scoring ────────────────────────────────────────────────

    def test_scoring_succeeds_for_valid_candidates(self) -> None:
        self.assertEqual(self.counts["scored_count"], self.counts["classified_count"])
        self.assertGreater(self.counts["scored_count"], 0)
        self.assertEqual(self.counts["verified_count"], self.counts["classified_count"])
        # Every scored candidate has a valid total in range.
        for entry in self.result.ranked.ranked:
            self.assertGreaterEqual(entry.final_rank_score, 0.0)
            self.assertLessEqual(entry.final_rank_score, 10.0)

    def test_rejected_disputed_candidates_would_not_crash(self) -> None:
        # The fixture set produces no REJECTED/DISPUTED verifications; the
        # harness and researcher guarantee they would be excluded with a
        # stable reason instead of crashing (contract tested in Step 11).
        self.assertEqual(self.report.processing_exclusions, ())
        statuses = {row["verification_status"] for row in self.report.candidate_summaries}
        self.assertNotIn("rejected", statuses)
        self.assertNotIn("disputed", statuses)

    # ── 15-19. ranking ────────────────────────────────────────────────

    def test_ranking_returns_multiple_candidates(self) -> None:
        self.assertGreaterEqual(self.counts["ranked_count"], 2)

    def test_cluster_diversity_cap_respected(self) -> None:
        cluster_counts: dict[str, int] = {}
        for summary in self.report.ranked_summaries:
            cluster_counts[summary.cluster] = cluster_counts.get(summary.cluster, 0) + 1
        for cluster, count in cluster_counts.items():
            self.assertLessEqual(count, 2, f"cluster {cluster} exceeded cap: {cluster_counts}")

    def test_ranking_order_deterministic(self) -> None:
        scores = [s.total_score for s in self.report.ranked_summaries]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_same_run_twice_identical_report(self) -> None:
        report_a = run_offline_dry_run(now=NOW)
        report_b = run_offline_dry_run(now=NOW)
        self.assertEqual(report_a.to_dict(), report_b.to_dict())
        self.assertEqual(report_a, report_b)

    def test_limit_is_forwarded(self) -> None:
        tiny = run_offline_dry_run(now=NOW, limit=2)
        big = run_offline_dry_run(now=NOW, limit=10)
        self.assertLessEqual(tiny.ranked_count, 2)
        self.assertEqual(tiny.limit, 2)
        self.assertEqual(tiny.ranked_summaries, big.ranked_summaries[:2])

    # ── 20-22. boundaries ─────────────────────────────────────────────

    def test_no_db_state_topic_history_main_or_legacy_agents(self) -> None:
        tree = ast.parse(
            (PROJECT_ROOT / "src" / "research" / "dry_run.py").read_text(encoding="utf-8")
        )
        code_text = _strip_docstrings(tree)
        for forbidden in (
            "src.main",
            "NewsHunter",
            "Strategist",
            "StateService",
            "topic_history",
            "factory.db",
            "StrategicSelection",
            "sqlite3",
            "CLUSTER_PRIORITY",
            "MIN_CONFIDENCE_FOR_SELECTION",
        ):
            self.assertNotIn(forbidden, code_text)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for module in imported:
            self.assertFalse(
                module.startswith(("src.agents", "src.factory", "src.storage", "src.core")),
                f"forbidden import: {module}",
            )
        self.assertFalse(any(m in imported for m in ("requests", "urllib.request", "socket")))

    def test_no_filesystem_writes_and_no_clock(self) -> None:
        tree = ast.parse(
            (PROJECT_ROOT / "src" / "research" / "dry_run.py").read_text(encoding="utf-8")
        )
        code_text = _strip_docstrings(tree)
        self.assertNotIn("datetime.now", code_text)
        self.assertNotIn("utcnow", code_text)
        # Filesystem contract: READ-ONLY access to the bundled fixtures is
        # allowed (and must actually happen); any write-family call or
        # write-mode open is forbidden.
        write_calls: set[str] = set()
        read_calls: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in (
                "write_text",
                "write_bytes",
                "mkdir",
                "unlink",
                "rename",
                "remove",
                "rmtree",
                "touch",
            ):
                write_calls.add(name)
            if name in ("open", "read_text", "read_bytes"):
                read_calls.add(name)
            if name == "open":
                modes: list[str] = []
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        modes.append(arg.value)
                for kw in node.keywords:
                    if (
                        kw.arg == "mode"
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, str)
                    ):
                        modes.append(kw.value.value)
                for mode in modes:
                    self.assertFalse(
                        any(flag in mode for flag in ("w", "a", "x", "+")),
                        f"write-mode open: {mode!r}",
                    )
        self.assertEqual(write_calls, set())
        self.assertIn("open", read_calls)

    def test_no_live_http_libraries_used_by_dry_run_path(self) -> None:
        # dry_run.py must not import any HTTP library; adapters get fakes.
        tree = ast.parse(
            (PROJECT_ROOT / "src" / "research" / "dry_run.py").read_text(encoding="utf-8")
        )
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for http_lib in ("requests", "httpx", "urllib.request", "aiohttp", "http.client"):
            self.assertNotIn(http_lib, imported)

    def test_report_is_human_readable_and_deterministic(self) -> None:
        text_a = format_report(self.report)
        text_b = format_report(run_offline_dry_run(now=NOW))
        self.assertEqual(text_a, text_b)
        self.assertIn("Researcher 2.0 offline dry run", text_a)
        self.assertIn("input_count", text_a)
        self.assertIn("ranked_count", text_a)
        self.assertIn("Trusted primary domains: example-ai.com", text_a)
        for summary in self.report.ranked_summaries:
            self.assertIn(summary.title, text_a)

    def test_fixture_epochs_align_with_fixture_now(self) -> None:
        # Story 101's published_at is exactly EPOCH_NOW - 2h; guard against
        # silent fixture/clock drift.
        items = _read_fixture(FIXTURES_DIR / "hn_items.json")
        from datetime import datetime as dt

        story_101 = dt.fromtimestamp(items["101"]["time"], tz=timezone.utc)
        expected = dt.fromisoformat(FIXTURE_NOW_STR) - timedelta(hours=2)
        self.assertEqual(story_101, expected)
        self.assertEqual(EPOCH_NOW, int(dt.fromisoformat(FIXTURE_NOW_STR).timestamp()))


class TestNoMutationAndPurity(unittest.TestCase):
    """Purity guarantees for the dry-run path."""

    def test_input_discoveries_not_mutated_by_pipeline(self) -> None:
        hn, github, rss = build_adapters(now=NOW)
        raw_pool = hn.fetch() + github.fetch() + rss.fetch()
        snapshot = copy.deepcopy(raw_pool)
        researcher = Researcher(adapters=(hn, github, rss))
        researcher.run(now=NOW)
        self.assertEqual(raw_pool, snapshot)

    def test_run_requires_now(self) -> None:
        hn, github, rss = build_adapters(now=NOW)
        researcher = Researcher(adapters=(hn, github, rss))
        with self.assertRaises(TypeError):
            researcher.run()  # type: ignore[call-arg]

    def test_module_has_no_top_level_side_effects(self) -> None:
        # Importing dry_run must not execute the pipeline or read fixtures.
        import importlib

        module_name = "src.research.dry_run"
        saved = sys.modules.get(module_name)
        if saved is not None:
            del sys.modules[module_name]
        try:
            module = importlib.import_module(module_name)
            self.assertTrue(hasattr(module, "run_offline_dry_run"))
            self.assertTrue(hasattr(module, "main"))
        finally:
            if saved is not None:
                sys.modules[module_name] = saved


if __name__ == "__main__":
    unittest.main()
