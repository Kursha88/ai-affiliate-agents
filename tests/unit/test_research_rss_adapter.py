"""Unit tests for the curated official RSS/Atom adapter (Step 10).

Covers the required matrix: RSS 2.0 and Atom parsing (title/link/
summary, published/updated timestamps with UTC normalization), feed
config validation (source_type restricted to OFFICIAL_BLOG/OFFICIAL_DOCS,
conservative trusted_domain validation, invalid limits), the
``trusted_primary_domains`` property derived only from curated configs
(no hardcoded vendors), guid/id preservation, conservative filtering
(missing title, invalid links, malformed entries isolated), same-feed
dedup by native entry id with normalized-URL fallback (cross-feed same
URL preserved, first occurrence wins, no fuzzy matching), limits,
failure isolation (one feed failing, partial success, all-feeds-fail ->
``safe_fetch`` failure), determinism, purity (no input mutation, no
live network), and structural guarantees (no
classification/verification/scoring/ranking, no DB/publishing, lazy
network import only, no local clock).

All fetches go through injected fakes; ZERO live network.
"""

from __future__ import annotations

import ast
import copy
import inspect
import unittest
from typing import Any, Dict, List, Optional

from src.domain.strategy import SourceType
from src.research.adapters.base import RawDiscovery, SourceAdapter
from src.research.adapters.rss import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_PER_FEED_LIMIT,
    OfficialFeed,
    OfficialRssAdapter,
    RSSFetchError,
    SUMMARY_MAX_CHARS,
)

BLOG = SourceType.OFFICIAL_BLOG
DOCS = SourceType.OFFICIAL_DOCS

FEED_A_URL = "https://example.com/blog/rss.xml"
FEED_B_URL = "https://other.example.org/notes/atom.xml"


def rss_feed(*items: str) -> str:
    body = "".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<channel><title>Example Blog</title>{body}</channel></rss>"
    )


def rss_item(
    title: str = "Post one",
    link: str = "https://example.com/blog/post-1",
    description: str = "Short summary of the post",
    pubdate: Optional[str] = "Mon, 07 Sep 2026 10:00:00 GMT",
    guid: Optional[str] = "guid-post-1",
    creator: bool = True,
) -> str:
    parts = [f"<title>{title}</title>", f"<link>{link}</link>"]
    if description is not None:
        parts.append(f"<description>{description}</description>")
    if pubdate is not None:
        parts.append(f"<pubDate>{pubdate}</pubDate>")
    if guid is not None:
        parts.append(f"<guid>{guid}</guid>")
    if creator:
        parts.append("<dc:creator>Jane Doe</dc:creator>")
    return "<item>" + "".join(parts) + "</item>"


def atom_feed(*entries: str) -> str:
    body = "".join(entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<title>Example Notes</title>"
        f"{body}</feed>"
    )


def atom_entry(
    title: str = "Note one",
    entry_id: str = "https://example.com/notes/1",
    link_href: str = "https://example.com/notes/1",
    link_extra: bool = True,
    summary: str = "Atom summary text",
    published: Optional[str] = "2026-09-07T10:00:00Z",
    updated: Optional[str] = "2026-09-07T11:00:00Z",
    author: bool = True,
) -> str:
    parts = [f"<title>{title}</title>"]
    if link_extra:
        parts.append('<link rel="replies" href="https://example.com/notes/1/comments"/>')
    if link_href is not None:
        parts.append(f'<link rel="alternate" href="{link_href}"/>')
    if summary is not None:
        parts.append(f"<summary>{summary}</summary>")
    if published is not None:
        parts.append(f"<published>{published}</published>")
    if updated is not None:
        parts.append(f"<updated>{updated}</updated>")
    if author:
        parts.append("<author><name>John Roe</name></author>")
    parts.append(f"<id>{entry_id}</id>")
    return "<entry>" + "".join(parts) + "</entry>"


def make_fetcher(
    responses: Dict[str, Any],
    *,
    calls: Optional[List[str]] = None,
) -> Any:
    def fetch_text(url: str) -> Optional[str]:
        if calls is not None:
            calls.append(url)
        return responses.get(url)

    return fetch_text


def make_adapter(
    responses: Dict[str, Any],
    *,
    feeds: Optional[tuple[OfficialFeed, ...]] = None,
    source_type: SourceType = BLOG,
    calls: Optional[List[str]] = None,
    **kwargs: Any,
) -> OfficialRssAdapter:
    feed_tuple = feeds if feeds is not None else (
        OfficialFeed("Example Blog", FEED_A_URL, "example.com"),
    )
    return OfficialRssAdapter(
        feed_tuple,
        source_type=source_type,
        fetch_text=make_fetcher(responses, calls=calls),
        **kwargs,
    )


# ══════════════════════════════════════════════════════════════════════
# Feed configuration
# ══════════════════════════════════════════════════════════════════════


class TestFeedConfig(unittest.TestCase):
    def test_valid_feed_config_and_domain_normalization(self):
        feed = OfficialFeed("  Blog  ", " https://example.com/rss ", "  WWW.Example.COM ")
        self.assertEqual(feed.name, "Blog")
        self.assertEqual(feed.feed_url, "https://example.com/rss")
        self.assertEqual(feed.trusted_domain, "example.com")

    def test_blank_name_rejected(self):
        for bad in ("", "   ", None, 42):
            with self.subTest(name=bad):
                with self.assertRaises(ValueError):
                    OfficialFeed(bad, FEED_A_URL, "example.com")  # type: ignore[arg-type]

    def test_invalid_feed_url_rejected(self):
        for bad in ("", "   ", "example.com/rss", "ftp://example.com/rss", "not a url"):
            with self.subTest(feed_url=bad):
                with self.assertRaises(ValueError):
                    OfficialFeed("Blog", bad, "example.com")  # type: ignore[arg-type]

    def test_malformed_trusted_domain_rejected(self):
        for bad in (
            "",
            "   ",
            None,
            "https://example.com",   # scheme
            "//example.com",
            "example.com/rss",       # path
            "user@example.com",      # credentials
            "example.com?x=1",       # query
            "example.com:443",       # port
            "localhost",             # not a dotted domain
            42,
        ):
            with self.subTest(trusted_domain=bad):
                with self.assertRaises(ValueError):
                    OfficialFeed("Blog", FEED_A_URL, bad)  # type: ignore[arg-type]

    def test_trusted_domain_is_neutral_metadata(self):
        # The config is plain data; nothing in it implies verification.
        feed = OfficialFeed("Blog", FEED_A_URL, "Example.com")
        self.assertEqual(feed.trusted_domain, "example.com")
        self.assertFalse(hasattr(feed, "verification"))


# ══════════════════════════════════════════════════════════════════════
# Adapter contract
# ══════════════════════════════════════════════════════════════════════


class TestAdapterContract(unittest.TestCase):
    def test_name_and_allowed_source_types(self):
        for source_type in (BLOG, DOCS):
            with self.subTest(source_type=source_type):
                adapter = make_adapter({}, source_type=source_type)
                self.assertEqual(adapter.name, "official_rss")
                self.assertEqual(adapter.source_type, source_type)
                self.assertIsInstance(adapter, SourceAdapter)

    def test_disallowed_source_type_rejected(self):
        for bad in (
            SourceType.HACKER_NEWS,
            SourceType.GITHUB,
            SourceType.REDDIT,
            SourceType.X,
            SourceType.OTHER,
            "official_blog",  # raw string is not a SourceType
        ):
            with self.subTest(source_type=bad):
                with self.assertRaises(ValueError):
                    make_adapter({}, source_type=bad)  # type: ignore[arg-type]

    def test_feeds_validation(self):
        with self.assertRaises(ValueError):
            make_adapter({}, feeds=())
        with self.assertRaises(ValueError):
            make_adapter({}, feeds=("not-a-feed",))  # type: ignore[list-item]

    def test_trusted_primary_domains_derived_from_configs(self):
        adapter = make_adapter(
            {},
            feeds=(
                OfficialFeed("Blog A", FEED_A_URL, "Example.com"),
                OfficialFeed("Blog B", FEED_B_URL, "other.example.org"),
                OfficialFeed("Blog C", "https://www.example.com/other.xml", "www.example.com"),
            ),
        )
        # Derived ONLY from the curated configs; lowercased; www. gone;
        # duplicates deduplicated in configuration order.
        self.assertEqual(
            adapter.trusted_primary_domains, ("example.com", "other.example.org")
        )

    def test_invalid_limits_raise(self):
        for value in (0, -3, 2.5, "10", None, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    make_adapter({}, per_feed_limit=value)  # type: ignore[arg-type]
                with self.assertRaises(ValueError):
                    make_adapter({}, max_results=value)  # type: ignore[arg-type]

    def test_conservative_defaults(self):
        self.assertEqual(DEFAULT_PER_FEED_LIMIT, 30)
        self.assertEqual(DEFAULT_MAX_RESULTS, 100)


# ══════════════════════════════════════════════════════════════════════
# RSS 2.0 parsing
# ══════════════════════════════════════════════════════════════════════


class TestRssParsing(unittest.TestCase):
    def _single(self, xml: str) -> RawDiscovery:
        result = make_adapter({FEED_A_URL: xml}).fetch()
        self.assertEqual(len(result), 1)
        return result[0]

    def test_rss_entry_mapping(self):
        record = self._single(rss_feed(rss_item()))
        self.assertEqual(record.title, "Post one")
        self.assertEqual(record.url, "https://example.com/blog/post-1")
        self.assertEqual(record.source_name, "Example Blog")
        self.assertEqual(record.summary, "Short summary of the post")
        self.assertIsNone(record.raw_score)
        self.assertIsNone(record.raw_score_label)
        self.assertIsNone(record.comments_count)

    def test_rss_timestamps_normalized_to_utc_iso(self):
        record = self._single(rss_feed(rss_item()))
        self.assertEqual(record.published_at, "2026-09-07T10:00:00+00:00")
        self.assertEqual(record.discovered_at, record.published_at)

    def test_rss_missing_pubdate_falls_back_to_empty_discovered_at(self):
        record = self._single(rss_feed(rss_item(pubdate=None)))
        self.assertIsNone(record.published_at)
        self.assertEqual(record.discovered_at, "")
        self.assertIsNone(record.metadata["published_raw"])

    def test_guid_preserved_as_namespaced_identifier(self):
        record = self._single(rss_feed(rss_item(guid="tag:example.com,2026:post-1")))
        self.assertEqual(
            record.identifiers, {"rss_entry_id": "tag:example.com,2026:post-1"}
        )
        self.assertEqual(record.metadata["entry_id"], "tag:example.com,2026:post-1")

    def test_entry_without_guid_has_no_identifier(self):
        record = self._single(rss_feed(rss_item(guid=None)))
        self.assertEqual(record.identifiers, {})
        self.assertIsNone(record.metadata["entry_id"])

    def test_dc_creator_retained_as_author(self):
        record = self._single(rss_feed(rss_item()))
        self.assertEqual(record.metadata["author"], "Jane Doe")

    def test_summary_html_stripped_conservatively(self):
        record = self._single(
            rss_feed(rss_item(description="<p>Big &amp; bold</p> <b>news</b>"))
        )
        self.assertEqual(record.summary, "Big & bold news")

    def test_long_summary_truncated(self):
        long_text = "x" * (SUMMARY_MAX_CHARS + 200)
        record = self._single(rss_feed(rss_item(description=long_text)))
        self.assertEqual(len(record.summary), SUMMARY_MAX_CHARS)

    def test_metadata_provenance(self):
        record = self._single(rss_feed(rss_item()))
        self.assertEqual(
            record.metadata["trusted_domain"], "example.com"
        )
        self.assertEqual(record.metadata["feed_url"], FEED_A_URL)
        self.assertEqual(record.metadata["source_format"], "rss")
        self.assertEqual(record.metadata["published_raw"], "Mon, 07 Sep 2026 10:00:00 GMT")


# ══════════════════════════════════════════════════════════════════════
# Atom parsing
# ══════════════════════════════════════════════════════════════════════


class TestAtomParsing(unittest.TestCase):
    def _single(self, xml: str) -> RawDiscovery:
        result = make_adapter(
            {FEED_A_URL: xml},
            feeds=(OfficialFeed("Example Notes", FEED_A_URL, "example.com"),),
        ).fetch()
        self.assertEqual(len(result), 1)
        return result[0]

    def test_atom_entry_mapping(self):
        record = self._single(atom_feed(atom_entry()))
        self.assertEqual(record.title, "Note one")
        # rel="alternate" preferred over rel="replies".
        self.assertEqual(record.url, "https://example.com/notes/1")
        self.assertEqual(record.summary, "Atom summary text")
        self.assertEqual(record.source_name, "Example Notes")
        self.assertEqual(record.metadata["source_format"], "atom")

    def test_atom_id_preserved(self):
        record = self._single(atom_feed(atom_entry(entry_id="urn:uuid:1234")))
        self.assertEqual(record.identifiers, {"rss_entry_id": "urn:uuid:1234"})

    def test_atom_author_name(self):
        record = self._single(atom_feed(atom_entry()))
        self.assertEqual(record.metadata["author"], "John Roe")

    def test_atom_published_preferred_over_updated(self):
        record = self._single(atom_feed(atom_entry()))
        self.assertEqual(record.published_at, "2026-09-07T10:00:00+00:00")
        self.assertEqual(record.metadata["published_raw"], "2026-09-07T10:00:00Z")
        self.assertEqual(record.metadata["updated_raw"], "2026-09-07T11:00:00Z")

    def test_atom_updated_fallback_when_published_missing(self):
        record = self._single(atom_feed(atom_entry(published=None)))
        self.assertEqual(record.published_at, "2026-09-07T11:00:00+00:00")
        self.assertIsNone(record.metadata["published_raw"])
        self.assertEqual(record.metadata["updated_raw"], "2026-09-07T11:00:00Z")

    def test_atom_offset_timestamps_normalized_to_utc(self):
        record = self._single(atom_feed(atom_entry(published="2026-09-07T12:00:00+02:00")))
        self.assertEqual(record.published_at, "2026-09-07T10:00:00+00:00")

    def test_atom_naive_timestamp_assumed_utc(self):
        record = self._single(atom_feed(atom_entry(published="2026-09-07T10:00:00")))
        self.assertEqual(record.published_at, "2026-09-07T10:00:00+00:00")

    def test_atom_unparseable_timestamp_kept_raw_only(self):
        record = self._single(
            atom_feed(atom_entry(published="not-a-date", updated="also-bad"))
        )
        self.assertIsNone(record.published_at)
        self.assertEqual(record.discovered_at, "")
        self.assertEqual(record.metadata["published_raw"], "not-a-date")
        self.assertEqual(record.metadata["updated_raw"], "also-bad")

    def test_atom_link_without_href_skipped(self):
        # ALL links lack href -> no usable link -> skipped.
        xml = atom_feed(atom_entry(link_href=None, link_extra=False))
        adapter = make_adapter(
            {FEED_A_URL: xml},
            feeds=(OfficialFeed("Example Notes", FEED_A_URL, "example.com"),),
        )
        self.assertEqual(adapter.fetch(), [])
        self.assertEqual(adapter.last_fetch_stats["skipped"]["missing_or_invalid_url"], 1)

    def test_atom_rel_alternate_preferred_over_other_rels(self):
        # A usable rel="replies" link IS a documented fallback when no
        # rel="alternate" exists — but "alternate" must win when both do.
        xml = atom_feed(atom_entry())  # replies + alternate present
        result = make_adapter(
            {FEED_A_URL: xml},
            feeds=(OfficialFeed("Example Notes", FEED_A_URL, "example.com"),),
        ).fetch()
        self.assertEqual(result[0].url, "https://example.com/notes/1")


# ══════════════════════════════════════════════════════════════════════
# Conservative filtering (per-entry isolation)
# ══════════════════════════════════════════════════════════════════════


class TestFiltering(unittest.TestCase):
    def _adapter(self, xml: str) -> OfficialRssAdapter:
        return make_adapter({FEED_A_URL: xml})

    def test_missing_title_skipped_others_kept(self):
        adapter = self._adapter(
            rss_feed(
                "<item><link>https://example.com/a</link></item>",
                rss_item(title="Good post", link="https://example.com/b", guid="g-b"),
            )
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Good post")
        self.assertEqual(adapter.last_fetch_stats["skipped"]["missing_title"], 1)

    def test_missing_or_invalid_link_skipped(self):
        adapter = self._adapter(
            rss_feed(
                "<item><title>No link</title></item>",
                rss_item(title="Bad scheme", link="javascript:alert(1)", guid="g-b"),
                rss_item(title="Bad relative", link="/blog/relative", guid="g-c"),
            )
        )
        result = adapter.fetch()
        self.assertEqual(result, [])
        # All three entries fail the link requirement (none, javascript:,
        # relative) — each skip is counted, never silent.
        self.assertEqual(adapter.last_fetch_stats["skipped"]["missing_or_invalid_url"], 3)

    def test_non_entry_garbage_never_kills_feed(self):
        adapter = self._adapter(
            rss_feed(
                "plain-text-noise",
                rss_item(title="Good post", link="https://example.com/b", guid="g-b"),
            )
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(adapter.last_fetch_stats["parsed"], 1)


# ══════════════════════════════════════════════════════════════════════
# In-adapter dedup
# ══════════════════════════════════════════════════════════════════════


class TestDedup(unittest.TestCase):
    def _two_feed_adapter(self, responses: Dict[str, Any]) -> OfficialRssAdapter:
        return make_adapter(
            responses,
            feeds=(
                OfficialFeed("Blog A", FEED_A_URL, "example.com"),
                OfficialFeed("Blog B", FEED_B_URL, "other.example.org"),
            ),
        )

    def test_same_entry_id_same_feed_dedups(self):
        xml = rss_feed(
            rss_item(title="First title", guid="guid-1"),
            rss_item(title="Second title", guid="guid-1"),
        )
        result = self._two_feed_adapter({FEED_A_URL: xml}).fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "First title")  # first occurrence wins

    def test_same_url_same_feed_dedups(self):
        xml = rss_feed(
            rss_item(title="First title", guid="guid-1", link="https://example.com/p"),
            rss_item(title="Second title", guid="guid-2", link="https://example.com/p"),
        )
        result = self._two_feed_adapter({FEED_A_URL: xml}).fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "First title")

    def test_same_url_normalized_variants_same_feed_dedup(self):
        xml = rss_feed(
            rss_item(title="First title", guid="guid-1", link="https://example.com/p"),
            rss_item(title="Second title", guid="guid-2", link="https://www.example.com/p?utm_source=x"),
        )
        result = self._two_feed_adapter({FEED_A_URL: xml}).fetch()
        self.assertEqual(len(result), 1)

    def test_url_fallback_used_when_no_entry_id(self):
        xml = rss_feed(
            rss_item(title="First title", guid=None, link="https://example.com/p"),
            rss_item(title="Second title", guid=None, link="https://example.com/p"),
        )
        result = self._two_feed_adapter({FEED_A_URL: xml}).fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "First title")

    def test_same_url_different_feed_preserved(self):
        item = rss_item()
        result = self._two_feed_adapter(
            {
                FEED_A_URL: rss_feed(item),
                FEED_B_URL: atom_feed(atom_entry()),
            }
        ).fetch()
        # Different official feeds are separate provenance records.
        self.assertEqual(len(result), 2)
        self.assertEqual({r.source_name for r in result}, {"Blog A", "Blog B"})

    def test_no_fuzzy_title_dedup(self):
        # Similar titles, DIFFERENT links and ids: preserved (no fuzzy
        # title matching anywhere in this adapter).
        xml = rss_feed(
            rss_item(
                title="Weekly AI Digest — September 8",
                guid="g-1",
                link="https://example.com/p/8",
            ),
            rss_item(
                title="Weekly AI Digest — September 9",
                guid="g-2",
                link="https://example.com/p/9",
            ),
        )
        result = self._two_feed_adapter({FEED_A_URL: xml}).fetch()
        self.assertEqual(len(result), 2)


# ══════════════════════════════════════════════════════════════════════
# Limits
# ══════════════════════════════════════════════════════════════════════


class TestLimits(unittest.TestCase):
    def _feed_with(self, count: int) -> str:
        return rss_feed(
            *[
                rss_item(title=f"Post {i}", guid=f"g-{i}", link=f"https://example.com/p/{i}")
                for i in range(count)
            ]
        )

    def test_per_feed_limit_enforced(self):
        adapter = make_adapter(
            {FEED_A_URL: self._feed_with(10)},
            per_feed_limit=4,
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 4)
        self.assertEqual(adapter.last_fetch_stats["parsed"], 4)

    def test_max_results_enforced(self):
        adapter = make_adapter(
            {
                FEED_A_URL: self._feed_with(5),
                FEED_B_URL: self._feed_with(5),
            },
            feeds=(
                OfficialFeed("Blog A", FEED_A_URL, "example.com"),
                OfficialFeed("Blog B", FEED_B_URL, "other.example.org"),
            ),
            max_results=7,
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 7)
        self.assertEqual(adapter.last_fetch_stats["kept"], 7)


# ══════════════════════════════════════════════════════════════════════
# Failure isolation
# ══════════════════════════════════════════════════════════════════════


class TestFailureIsolation(unittest.TestCase):
    def _two_feed_adapter(self, responses: Dict[str, Any]) -> OfficialRssAdapter:
        return make_adapter(
            responses,
            feeds=(
                OfficialFeed("Blog A", FEED_A_URL, "example.com"),
                OfficialFeed("Blog B", FEED_B_URL, "other.example.org"),
            ),
        )

    def test_one_feed_failure_isolated(self):
        adapter = self._two_feed_adapter(
            {
                FEED_A_URL: None,  # fetch failed
                FEED_B_URL: atom_feed(atom_entry()),
            }
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 1)
        stats = adapter.last_fetch_stats
        self.assertEqual(stats["requested_feeds"], 2)
        self.assertEqual(stats["failed_feeds"], 1)
        self.assertEqual(stats["feed_errors"]["Blog A"], "fetch_failed")
        self.assertEqual(stats["kept"], 1)

    def test_malformed_feed_xml_isolated_and_counted(self):
        adapter = self._two_feed_adapter(
            {
                FEED_A_URL: "<rss><channel><unclosed>",
                FEED_B_URL: rss_feed(rss_item()),
            }
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(adapter.last_fetch_stats["feed_errors"]["Blog A"], "malformed_feed_xml")

    def test_unsupported_feed_format_isolated(self):
        adapter = self._two_feed_adapter(
            {
                FEED_A_URL: "<html><body>not a feed</body></html>",
                FEED_B_URL: rss_feed(rss_item()),
            }
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(adapter.last_fetch_stats["feed_errors"]["Blog A"], "unsupported_feed_format")

    def test_all_feeds_fail_raises_and_safe_fetch_reports(self):
        adapter = self._two_feed_adapter({FEED_A_URL: None, FEED_B_URL: "<broken"})
        with self.assertRaises(RSSFetchError):
            adapter.fetch()
        discoveries = adapter.safe_fetch()
        self.assertEqual(discoveries, [])
        self.assertIsNotNone(adapter.last_error)
        self.assertIn("RSSFetchError", adapter.last_error)

    def test_partial_success_returns_records_and_stats(self):
        adapter = self._two_feed_adapter(
            {
                FEED_A_URL: rss_feed(rss_item(), rss_item(guid="g-2", link="https://example.com/p/2")),
                FEED_B_URL: None,
            }
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 2)
        stats = adapter.last_fetch_stats
        self.assertEqual(stats["failed_feeds"], 1)
        self.assertEqual(stats["parsed"], 2)
        self.assertEqual(stats["kept"], 2)


# ══════════════════════════════════════════════════════════════════════
# Determinism, purity, structure
# ══════════════════════════════════════════════════════════════════════


class TestDeterminismPurityStructure(unittest.TestCase):
    def _responses(self) -> Dict[str, Any]:
        return {
            FEED_A_URL: rss_feed(
                rss_item(),
                rss_item(title="Post two", guid="g-2", link="https://example.com/p/2"),
            ),
            FEED_B_URL: atom_feed(atom_entry()),
        }

    def _two_feed_adapter(self, responses: Dict[str, Any]) -> OfficialRssAdapter:
        return make_adapter(
            responses,
            feeds=(
                OfficialFeed("Blog A", FEED_A_URL, "example.com"),
                OfficialFeed("Blog B", FEED_B_URL, "other.example.org"),
            ),
        )

    def test_deterministic_output(self):
        first = self._two_feed_adapter(self._responses()).fetch()
        second = self._two_feed_adapter(self._responses()).fetch()
        self.assertEqual(first, second)
        self.assertEqual(
            [r.source_name for r in first], ["Blog A", "Blog A", "Blog B"]
        )

    def test_raw_discovery_not_mutated_and_frozen(self):
        import copy as copy_module

        record = self._two_feed_adapter(self._responses()).fetch()[0]
        snapshot = copy_module.deepcopy(record)
        with self.assertRaises((AttributeError, TypeError)):
            record.title = "mutated"  # type: ignore[misc]
        self.assertIsInstance(record, RawDiscovery)
        self.assertEqual(record, snapshot)

    def test_no_live_network_required(self):
        calls: List[str] = []
        adapter = make_adapter(self._responses(), feeds=(
            OfficialFeed("Blog A", FEED_A_URL, "example.com"),
            OfficialFeed("Blog B", FEED_B_URL, "other.example.org"),
        ), calls=calls)
        self.assertEqual(calls, [])  # nothing fetched before fetch()
        adapter.fetch()
        self.assertEqual(sorted(calls), sorted([FEED_A_URL, FEED_B_URL]))

    def test_no_classification_verification_scoring_ranking_or_db(self):
        from src.research.adapters import rss as rss_module

        tree = ast.parse(inspect.getsource(rss_module))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        self.assertFalse(
            imported
            & {
                "src.research.classify",
                "src.research.verify",
                "src.research.score",
                "src.research.rank",
                "src.research.dedup",
                "sqlite3",
                "os",
                "subprocess",
                "src.main",
                "src.storage",
                "src.factory",
                "src.agents",
                "src.integrations",
            }
        )
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for forbidden in (
            "classify",
            "verify_provenance",
            "score_candidate",
            "rank_candidates",
            "CandidateScore",
            "VerificationResult",
            "ClassificationResult",
            "StrategicSelection",
        ):
            self.assertNotIn(forbidden, names)

    def test_lazy_network_import_only(self):
        # ``requests`` is allowed ONLY inside default_fetch_text —
        # never at module level, never in business logic.
        from src.research.adapters import rss as rss_module

        tree = ast.parse(inspect.getsource(rss_module))
        lazy_nodes = {
            id(node)
            for fn in ast.walk(tree)
            if isinstance(fn, ast.FunctionDef) and fn.name == "default_fetch_text"
            for node in ast.walk(fn)
            if isinstance(node, ast.Import)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == "requests" for alias in node.names
            ):
                self.assertIn(id(node), lazy_nodes, "requests import must be lazy")

    def test_no_hardcoded_vendor_domains(self):
        from src.research.adapters import rss as rss_module

        source = inspect.getsource(rss_module).lower()
        for vendor in (
            "openai", "anthropic", "google.com", "meta.com", "microsoft",
            "huggingface", "deepmind", "techcrunch",
        ):
            self.assertNotIn(vendor, source)

    def test_no_local_clock(self):
        from src.research.adapters import rss as rss_module

        tree = ast.parse(inspect.getsource(rss_module))
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    node.body = body[1:]
        source = ast.unparse(tree)
        self.assertNotIn("datetime.now", source)
        self.assertNotIn("utcnow", source)


if __name__ == "__main__":
    unittest.main()
