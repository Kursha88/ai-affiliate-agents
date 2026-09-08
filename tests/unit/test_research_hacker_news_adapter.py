"""Unit tests for the Hacker News adapter (Stage 3.2 Step 3).

All tests run offline against the JSON fixtures in
``tests/fixtures/research/`` through an injected fake fetcher — zero
live network calls.

Coverage: adapter identity, the source-URL rule (outbound vs HN-native),
source-level filtering branches, provenance metadata, timestamps,
per-item failure isolation, topstories envelope failure, and the
no-classification / no-scoring / no-ranking boundary.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.domain.strategy import SourceType
from src.research.adapters.base import RawDiscovery
from src.research.adapters.hacker_news import (
    HN_API_BASE,
    HackerNewsAdapter,
    HackerNewsFetchError,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "research"

#: Reference 'now' used by the fixtures: 2026-09-08T12:00:00Z.
FIXED_NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def _load_fixture(name: str):
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


def make_fake_fetcher():
    """Fixture-driven fake fetcher: URL -> parsed JSON (or None)."""
    topstories = _load_fixture("hn_topstories.json")["story_ids"]
    items = _load_fixture("hn_items.json")["items"]

    def fetch_json(url: str):
        if url == f"{HN_API_BASE}/topstories.json":
            return list(topstories)
        prefix = f"{HN_API_BASE}/item/"
        if url.startswith(prefix):
            item_id = url[len(prefix):].removesuffix(".json")
            return items.get(item_id)
        return None

    return fetch_json


def make_adapter(**kwargs) -> HackerNewsAdapter:
    defaults = dict(fetch_json=make_fake_fetcher(), now_fn=lambda: FIXED_NOW)
    defaults.update(kwargs)
    return HackerNewsAdapter(**defaults)


class TestAdapterIdentity(unittest.TestCase):
    def test_name_is_stable(self) -> None:
        self.assertEqual(make_adapter().name, "hacker_news")

    def test_source_type_is_hacker_news(self) -> None:
        self.assertEqual(make_adapter().source_type, SourceType.HACKER_NEWS)

    def test_returns_raw_discovery_records(self) -> None:
        results = make_adapter().safe_fetch()
        self.assertTrue(results)
        self.assertTrue(all(isinstance(r, RawDiscovery) for r in results))


class TestSourceUrlRule(unittest.TestCase):
    def setUp(self) -> None:
        self.records = {r.identifiers["hn_item_id"]: r for r in make_adapter().safe_fetch()}

    def test_normal_story_keeps_outbound_url(self) -> None:
        record = self.records["999999901"]
        # Outbound URL is the discovery's source URL (normalized? no —
        # the adapter stores the raw outbound URL; normalization happens
        # in the normalize/dedup stages).
        self.assertEqual(record.url, "https://github.com/example/vibe-tool?utm_source=hackernews")
        self.assertFalse(record.metadata["hn_native"])

    def test_discussion_url_kept_separately_in_metadata(self) -> None:
        record = self.records["999999901"]
        self.assertEqual(
            record.metadata["hn_item_url"],
            "https://news.ycombinator.com/item?id=999999901",
        )

    def test_native_story_uses_discussion_url_and_is_marked(self) -> None:
        record = self.records["999999902"]
        self.assertEqual(record.url, "https://news.ycombinator.com/item?id=999999902")
        self.assertTrue(record.metadata["hn_native"])


class TestFiltering(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = make_adapter()
        self.records = self.adapter.safe_fetch()
        self.ids = {r.identifiers["hn_item_id"] for r in self.records}

    def test_dead_item_skipped(self) -> None:
        self.assertNotIn("999999904", self.ids)
        self.assertIn("dead_or_deleted", self.adapter.last_fetch_stats["skipped"])

    def test_unsupported_type_skipped(self) -> None:
        self.assertNotIn("999999905", self.ids)
        self.assertIn("unsupported_type", self.adapter.last_fetch_stats["skipped"])

    def test_blank_title_skipped(self) -> None:
        self.assertNotIn("999999906", self.ids)
        self.assertIn("missing_title", self.adapter.last_fetch_stats["skipped"])

    def test_too_old_story_skipped(self) -> None:
        self.assertNotIn("999999907", self.ids)
        self.assertIn("too_old", self.adapter.last_fetch_stats["skipped"])

    def test_missing_time_skipped(self) -> None:
        self.assertNotIn("999999908", self.ids)
        self.assertIn("missing_time", self.adapter.last_fetch_stats["skipped"])

    def test_missing_item_skipped_in_isolation(self) -> None:
        self.assertNotIn("999999903", self.ids)
        self.assertIn("unavailable", self.adapter.last_fetch_stats["skipped"])

    def test_valid_items_survive_siblings_failures(self) -> None:
        self.assertEqual(
            self.ids, {"999999901", "999999902"},
            "exactly the two valid stories must be kept",
        )
        self.assertEqual(self.adapter.last_fetch_stats["kept"], 2)
        self.assertEqual(self.adapter.last_fetch_stats["requested"], 8)


class TestProvenance(unittest.TestCase):
    def setUp(self) -> None:
        self.records = {r.identifiers["hn_item_id"]: r for r in make_adapter().safe_fetch()}

    def test_points_stored_as_raw_score_label(self) -> None:
        record = self.records["999999901"]
        self.assertEqual(record.raw_score, 412)
        self.assertEqual(record.raw_score_label, "hn_points")

    def test_comments_and_author_retained(self) -> None:
        record = self.records["999999901"]
        self.assertEqual(record.comments_count, 57)
        self.assertEqual(record.metadata["author"], "alice")

    def test_item_id_retained_as_identifier(self) -> None:
        self.assertEqual(
            self.records["999999901"].identifiers,
            {"hn_item_id": "999999901"},
        )

    def test_published_at_converted_to_iso_z(self) -> None:
        record = self.records["999999901"]
        # Epoch 1788861600 == 2026-09-08T10:00:00Z.
        self.assertEqual(record.published_at, "2026-09-08T10:00:00Z")
        self.assertEqual(record.discovered_at, "2026-09-08T12:00:00Z")

    def test_age_hours_present(self) -> None:
        self.assertEqual(self.records["999999901"].metadata["age_hours"], 2.0)

    def test_item_type_recorded(self) -> None:
        self.assertEqual(
            self.records["999999901"].metadata["hn_item_type"], "story"
        )


class TestFailureIsolation(unittest.TestCase):
    def test_topstories_failure_raises_inside_fetch(self) -> None:
        adapter = HackerNewsAdapter(fetch_json=lambda url: None, now_fn=lambda: FIXED_NOW)
        with self.assertRaises(HackerNewsFetchError):
            adapter.fetch()

    def test_topstories_failure_isolated_by_safe_fetch(self) -> None:
        adapter = HackerNewsAdapter(fetch_json=lambda url: None, now_fn=lambda: FIXED_NOW)
        self.assertEqual(adapter.safe_fetch(), [])
        self.assertIsNotNone(adapter.last_error)
        self.assertIn("topstories", adapter.last_error)

    def test_topstories_wrong_type_is_envelope_failure(self) -> None:
        adapter = HackerNewsAdapter(fetch_json=lambda url: {}, now_fn=lambda: FIXED_NOW)
        self.assertEqual(adapter.safe_fetch(), [])
        self.assertIsNotNone(adapter.last_error)

    def test_item_fetch_none_is_isolated_skip(self) -> None:
        base = make_fake_fetcher()

        def fetch_json(url: str):
            if "/item/" in url:
                return None  # every item unavailable
            return base(url)

        adapter = HackerNewsAdapter(fetch_json=fetch_json, now_fn=lambda: FIXED_NOW)
        self.assertEqual(adapter.safe_fetch(), [])
        self.assertEqual(adapter.last_fetch_stats["skipped"]["unavailable"], 8)
        self.assertIsNone(adapter.last_error)  # envelope-level: cycle itself healthy


class TestBoundaryGuarantees(unittest.TestCase):
    """The adapter must not classify, verify, score or rank."""

    def setUp(self) -> None:
        self.records = make_adapter().safe_fetch()

    def test_no_classification_fields(self) -> None:
        for record in self.records:
            self.assertFalse(hasattr(record, "content_cluster"))

    def test_no_composite_score_computed(self) -> None:
        # raw_score is the HN-native point value, nothing derived.
        for record in self.records:
            self.assertEqual(record.raw_score_label, "hn_points")
        self.assertEqual(
            self.records_map()["999999901"].raw_score, 412
        )

    def records_map(self) -> dict:
        return {r.identifiers["hn_item_id"]: r for r in self.records}

    def test_no_ranking_reordering(self) -> None:
        # Fixture order: 901 (412 pts), 902 (88 pts). HN-native topstories
        # order must be preserved; the adapter must not sort by score.
        ids = [r.identifiers["hn_item_id"] for r in self.records]
        self.assertEqual(ids, ["999999901", "999999902"])

    def test_no_verification_fields(self) -> None:
        for record in self.records:
            for forbidden in ("verification_status", "confidence", "total_score"):
                self.assertFalse(hasattr(record, forbidden))

    def test_module_does_not_import_strategy_scoring_or_classifier(self) -> None:
        # Structural check (not source-text matching, which false-positives
        # on docstrings that document the boundary): the module must not
        # expose Stage 3.1 scoring/classification symbols, and the adapter
        # class must not implement classify/verify/score/rank behavior.
        import src.research.adapters.hacker_news as hn_module

        public_symbols = {
            name for name in dir(hn_module) if not name.startswith("_")
        }
        forbidden_symbols = {
            "CandidateScore",
            "CLUSTER_PRIORITY",
            "DiscoveryCandidate",
            "VerificationResult",
            "classify",
            "verify",
            "score",
            "rank",
        }
        self.assertEqual(public_symbols & forbidden_symbols, set())

        # Allowed Stage 3.1 dependency is the explicit source identity only.
        self.assertTrue(hasattr(hn_module, "SourceType"))

        for method in ("classify", "verify", "score", "rank", "compute_score"):
            self.assertFalse(
                hasattr(HackerNewsAdapter, method),
                f"adapter must not implement '{method}'",
            )


if __name__ == "__main__":
    unittest.main()
