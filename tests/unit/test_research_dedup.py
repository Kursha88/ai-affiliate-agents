"""Unit tests for Stage 3.2 conservative discovery deduplication.

Covers the three identity layers (namespaced native identifiers,
same-source canonical URL, exact-title fallback), cross-source
provenance preservation, malformed-data tolerance, determinism,
observability, and structural guarantees (no fuzzy matching, no
classification/scoring/ranking, no DB/network/publishing imports, no
``CLUSTER_PRIORITY``, no ``RawDiscovery`` mutation).

All inputs are in-memory ``RawDiscovery`` records; no network access.
"""

from __future__ import annotations

import ast
import copy
import inspect
import unittest

from src.research.adapters.base import RawDiscovery
from src.research.dedup import (
    REASON_CANONICAL_URL_SAME_SOURCE,
    REASON_EXACT_TITLE_SAME_SOURCE,
    REASON_NATIVE_IDENTIFIER,
    DeduplicationResult,
    deduplicate,
)


def make_discovery(
    title: str,
    url: str | None = "https://example.com/article",
    source_name: str = "hacker_news",
    identifiers: dict | None = None,
    metadata: dict | None = None,
) -> RawDiscovery:
    return RawDiscovery(
        title=title,
        url=url,
        source_name=source_name,
        discovered_at="2026-09-08T12:00:00Z",
        identifiers=identifiers if identifiers is not None else {},
        metadata=metadata if metadata is not None else {},
    )


class TestNativeIdentifierLayer(unittest.TestCase):
    """Layer 1: namespaced source-native identifiers."""

    def test_same_hn_item_id_dedups(self):
        first = make_discovery("Story One", identifiers={"hn_item_id": "123"})
        second = make_discovery("Story One (duplicate)", identifiers={"hn_item_id": "123"})
        result = deduplicate([first, second])
        self.assertEqual(result.output_count, 1)
        self.assertEqual(result.duplicate_count, 1)
        self.assertEqual(
            result.duplicate_groups[0].reason, REASON_NATIVE_IDENTIFIER
        )

    def test_different_namespaces_never_collide_on_value(self):
        # hn_item_id=123 vs a generic/unrelated id=123 must NOT dedup.
        records = [
            make_discovery("HN story", identifiers={"hn_item_id": "123"}),
            make_discovery("Other record", source_name="other", identifiers={"record_id": "123"}),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)
        self.assertEqual(result.duplicate_count, 0)

    def test_generic_id_key_is_ignored_entirely(self):
        # id=123 must never collide with hn_item_id=123 ...
        records = [
            make_discovery("HN story", url=None, identifiers={"hn_item_id": "123"}),
            make_discovery("Generic record", url=None, source_name="other", identifiers={"id": "123"}),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)
        # ... and two generic id=123 records must not dedup with each other
        # (url=None so the same-source URL layer cannot mask the assertion).
        result = deduplicate(
            [
                make_discovery("A", url=None, source_name="x", identifiers={"id": "123"}),
                make_discovery("B", url=None, source_name="x", identifiers={"id": "123"}),
            ]
        )
        self.assertEqual(result.output_count, 2)

    def test_different_hn_item_ids_do_not_dedup(self):
        # url=None + distinct titles: only the (non-firing) native layer
        # could collapse these — the same-source URL layer must not.
        records = [
            make_discovery("Story One", url=None, identifiers={"hn_item_id": "123"}),
            make_discovery("Story Two", url=None, identifiers={"hn_item_id": "456"}),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)

    def test_malformed_identifier_ignored(self):
        # url=None + distinct titles so only identifier identity is tested.
        records = [
            make_discovery("HN story", url=None, identifiers={"hn_item_id": "123"}),
            # None / blank values are ignored conservatively.
            make_discovery("Odd record", url=None, identifiers={"hn_item_id": None, "x_id": "   "}),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)

    def test_missing_identifiers_valid(self):
        # url=None + distinct titles: nothing to match on -> both preserved.
        result = deduplicate(
            [make_discovery("A", url=None), make_discovery("B", url=None)]
        )
        self.assertEqual(result.output_count, 2)

    def test_github_repo_identifier_dedups_only_when_record_represents_repo(self):
        # Adapter-declared github_repo identity on repo-representing records.
        records = [
            make_discovery(
                "Foo — the repository",
                url="https://github.com/org/foo",
                identifiers={"github_repo": "org/foo"},
            ),
            make_discovery(
                "Foo — mirror announcement",
                url="https://github.com/org/foo",
                identifiers={"github_repo": "org/foo"},
            ),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 1)
        self.assertEqual(
            result.duplicate_groups[0].reason, REASON_NATIVE_IDENTIFIER
        )

    def test_github_repo_identity_not_inferred_from_metadata(self):
        # Example B: an article about a project and the project's repo are
        # NOT duplicates even when metadata references the same project.
        records = [
            make_discovery(
                "New coding agent Foo released",
                url="https://techcrunch.com/foo",
                source_name="hacker_news",
                metadata={"project": "github.com/org/foo"},
            ),
            make_discovery(
                "Foo repository",
                url="https://github.com/org/foo",
                source_name="github",
            ),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)
        self.assertEqual(result.duplicate_count, 0)


class TestCanonicalUrlLayer(unittest.TestCase):
    """Layer 2: canonical URL identity within the same provenance."""

    def test_same_normalized_url_same_source_dedups(self):
        records = [
            make_discovery("Tool launch", url="https://example.com/tool"),
            make_discovery("Tool launch", url="https://example.com/tool"),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 1)
        self.assertEqual(
            result.duplicate_groups[0].reason, REASON_CANONICAL_URL_SAME_SOURCE
        )

    def test_tracking_param_variants_same_source_dedup(self):
        # Example C: same adapter, tracker-laden and clean URLs.
        records = [
            make_discovery("Tool", url="https://example.com/tool?utm_source=hn"),
            make_discovery("Tool", url="https://www.example.com/tool/"),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 1)
        group = result.duplicate_groups[0]
        self.assertEqual(group.reason, REASON_CANONICAL_URL_SAME_SOURCE)
        self.assertEqual(group.identity_key, "canonical_url=https://example.com/tool")

    def test_www_and_root_slash_normalization_same_source_dedup(self):
        records = [
            make_discovery("Docs", url="https://www.example.com/"),
            make_discovery("Docs", url="https://example.com"),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 1)

    def test_same_url_across_different_source_types_preserved(self):
        # Example A: HN story and the official blog covering the same
        # announcement are independent provenance — both preserved.
        records = [
            make_discovery(
                "OpenAI launches new model",
                url="https://openai.com/example",
                source_name="hacker_news",
            ),
            make_discovery(
                "Introducing our new model",
                url="https://openai.com/example",
                source_name="official_blog",
            ),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)
        self.assertEqual(result.duplicate_count, 0)

    def test_same_url_across_different_source_names_preserved(self):
        records = [
            make_discovery("Article", url="https://example.com/a", source_name="hn_feed_1"),
            make_discovery("Article", url="https://example.com/a", source_name="hn_feed_2"),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)

    def test_url_layer_requires_non_blank_source_name(self):
        # Conservative: no provenance -> URL layer does not collapse.
        records = [
            make_discovery("A", url="https://example.com/x", source_name="  "),
            make_discovery("B", url="https://example.com/x", source_name=""),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)

    def test_malformed_url_does_not_crash(self):
        records = [
            make_discovery("Bad one", url="not a url at all"),
            make_discovery("Bad two", url="ftp://example.com/file"),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)

    def test_missing_url_does_not_crash(self):
        records = [
            make_discovery("No url one", url=None),
            make_discovery("No url two", url=None),
        ]
        result = deduplicate(records)
        # No ID, no URL, same source, different titles -> preserved.
        self.assertEqual(result.output_count, 2)


class TestTitleFallbackLayer(unittest.TestCase):
    """Layer 3: exact normalized title, same source, no ID, no URL."""

    def test_exact_title_same_source_no_id_no_url_dedups(self):
        records = [
            make_discovery("Weekly AI News Digest — September 8", url=None),
            make_discovery("Weekly AI News Digest — September 8", url=None),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 1)
        self.assertEqual(
            result.duplicate_groups[0].reason, REASON_EXACT_TITLE_SAME_SOURCE
        )

    def test_exact_title_normalized_form_dedups(self):
        # Normalization folds quotes/dashes/case — conservative exact match.
        records = [
            make_discovery("The \u201cAgentic\u201d Future", url=None),
            make_discovery('the "agentic" future', url=None),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 1)

    def test_exact_title_across_different_sources_preserved(self):
        records = [
            make_discovery("Same title", url=None, source_name="hacker_news"),
            make_discovery("Same title", url=None, source_name="rss_blog"),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)

    def test_similar_but_not_identical_titles_preserved(self):
        records = [
            make_discovery("Weekly AI News Digest — September 8", url=None),
            make_discovery("Weekly AI News Digest — September 9", url=None),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)

    def test_title_fallback_requires_no_url(self):
        # Same title, same source, but both have URLs -> URL layer governs,
        # title fallback must not fire.
        records = [
            make_discovery("Same title", url="https://example.com/1"),
            make_discovery("Same title", url="https://example.com/2"),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)

    def test_blank_title_does_not_create_identity(self):
        records = [
            make_discovery("", url=None),
            make_discovery("", url=None),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)


class TestCrossSourceProvenance(unittest.TestCase):
    """Independent coverage survives; duplicates stay within a source."""

    def test_hn_vs_official_blog_same_event_preserved(self):
        records = [
            make_discovery(
                "OpenAI launches new model",
                url="https://openai.com/example",
                source_name="hacker_news",
                identifiers={"hn_item_id": "999"},
            ),
            make_discovery(
                "Introducing our new model",
                url="https://openai.com/example",
                source_name="official_blog",
            ),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)

    def test_cross_source_same_title_preserved(self):
        records = [
            make_discovery(
                "OpenAI launches X",
                url="https://techcrunch.com/openai-x",
                source_name="techcrunch_rss",
            ),
            make_discovery(
                "OpenAI launches X",
                url="https://techcrunch.com/openai-x",
                source_name="hacker_news",
            ),
        ]
        result = deduplicate(records)
        self.assertEqual(result.output_count, 2)

    def test_two_hn_discussions_same_outbound_url_conservative_contract(self):
        # Requirement 24: same hn_item_id => definite duplicate (layer 1).
        same_id = deduplicate(
            [
                make_discovery("X launch", url="https://example.com/x", identifiers={"hn_item_id": "777"}),
                make_discovery("X launch", url="https://example.com/x", identifiers={"hn_item_id": "777"}),
            ]
        )
        self.assertEqual(same_id.output_count, 1)
        self.assertEqual(same_id.duplicate_groups[0].reason, REASON_NATIVE_IDENTIFIER)

        # Different HN discussions sharing an outbound URL: distinct strong
        # native IDs are explicit evidence the source considers the records
        # distinct — BOTH are preserved (Step 5.1). The URL layer must not
        # override native-ID distinction.
        different_ids = deduplicate(
            [
                make_discovery("X launch", url="https://example.com/x", identifiers={"hn_item_id": "777"}),
                make_discovery("X launch (repost)", url="https://example.com/x", identifiers={"hn_item_id": "888"}),
            ]
        )
        self.assertEqual(different_ids.output_count, 2)
        self.assertEqual(different_ids.duplicate_count, 0)
        self.assertEqual(
            [item.identifiers["hn_item_id"] for item in different_ids.items],
            ["777", "888"],
        )


class TestOrderDeterminismObservability(unittest.TestCase):
    """Stable order, first-occurrence wins, deterministic, observable."""

    def test_first_occurrence_wins(self):
        records = [
            make_discovery("First", identifiers={"hn_item_id": "1"}),
            make_discovery("Second", identifiers={"hn_item_id": "1"}),
        ]
        result = deduplicate(records)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].title, "First")
        self.assertEqual(result.duplicate_groups[0].kept.title, "First")

    def test_input_order_preserved(self):
        titles = ["c first", "a second", "b third"]
        records = [make_discovery(t, url=None) for t in titles]
        result = deduplicate(records)
        self.assertEqual([item.title for item in result.items], titles)

    def test_duplicate_groups_observable(self):
        records = [
            make_discovery("A", url="https://example.com/1"),
            make_discovery("A dup", url="https://example.com/1?utm_source=x"),
            make_discovery("A dup 2", url="https://example.com/1"),
        ]
        result = deduplicate(records)
        self.assertEqual(len(result.duplicate_groups), 1)
        group = result.duplicate_groups[0]
        self.assertEqual(group.kept_index, 0)
        self.assertEqual(group.removed_indexes, (1, 2))
        self.assertEqual(len(group.removed), 2)

    def test_counts_correct(self):
        records = [
            make_discovery("A", url="https://example.com/1"),
            make_discovery("A dup", url="https://example.com/1"),
            make_discovery("B", url="https://example.com/2"),
            make_discovery("B dup", url="https://example.com/2"),
            make_discovery("C", url="https://example.com/3"),
        ]
        result = deduplicate(records)
        self.assertEqual(result.input_count, 5)
        self.assertEqual(result.output_count, 3)
        self.assertEqual(result.duplicate_count, 2)

    def test_deterministic_repeated_calls(self):
        records = [
            make_discovery("A", url="https://example.com/1", identifiers={"hn_item_id": "1"}),
            make_discovery("A dup", url="https://example.com/1?utm_source=t"),
            make_discovery("B", url=None),
            make_discovery("B", url=None),
        ]
        first = deduplicate(records)
        second = deduplicate(records)
        self.assertEqual(first, second)

    def test_empty_input(self):
        result = deduplicate([])
        self.assertEqual(result.input_count, 0)
        self.assertEqual(result.output_count, 0)
        self.assertEqual(result.duplicate_count, 0)
        self.assertEqual(result.items, ())
        self.assertEqual(result.duplicate_groups, ())

    def test_raw_discovery_objects_not_mutated(self):
        records = [
            make_discovery("A", url="https://example.com/1?utm_source=x", identifiers={"hn_item_id": "1"}),
            make_discovery("A dup", url="https://example.com/1", identifiers={"hn_item_id": "1"}),
        ]
        snapshot = [copy.deepcopy(r) for r in records]
        deduplicate(records)
        self.assertEqual(records, snapshot)

    def test_result_contract_shape(self):
        result = deduplicate([make_discovery("A")])
        self.assertIsInstance(result, DeduplicationResult)
        payload_groups = result.duplicate_groups  # empty here; shape via non-empty case below
        run = deduplicate(
            [
                make_discovery("A", url="https://example.com/1"),
                make_discovery("A dup", url="https://example.com/1"),
            ]
        )
        self.assertIsNone(payload_groups or None)
        group = run.duplicate_groups[0]
        self.assertEqual(
            {field for field in group.__dataclass_fields__},
            {"reason", "identity_key", "kept_index", "kept", "removed_indexes", "removed"},
        )


class TestNativeIdPrecedence(unittest.TestCase):
    """Step 5.1: the URL layer must not override native-ID distinction."""

    def test_same_hn_id_same_url_dedups_via_native_identifier(self):
        result = deduplicate(
            [
                make_discovery("Tool", url="https://example.com/tool", identifiers={"hn_item_id": "111"}),
                make_discovery("Tool", url="https://example.com/tool", identifiers={"hn_item_id": "111"}),
            ]
        )
        self.assertEqual(result.output_count, 1)
        self.assertEqual(
            result.duplicate_groups[0].reason, REASON_NATIVE_IDENTIFIER
        )

    def test_same_hn_id_different_url_dedups_via_native_identifier(self):
        result = deduplicate(
            [
                make_discovery("Tool", url="https://example.com/tool", identifiers={"hn_item_id": "111"}),
                make_discovery("Tool", url="https://example.com/tool?utm_source=x", identifiers={"hn_item_id": "111"}),
            ]
        )
        self.assertEqual(result.output_count, 1)
        self.assertEqual(
            result.duplicate_groups[0].reason, REASON_NATIVE_IDENTIFIER
        )

    def test_different_hn_ids_same_url_preserve_both(self):
        result = deduplicate(
            [
                make_discovery("Tool", url="https://example.com/tool", identifiers={"hn_item_id": "111"}),
                make_discovery("Tool", url="https://example.com/tool", identifiers={"hn_item_id": "222"}),
            ]
        )
        self.assertEqual(result.output_count, 2)
        self.assertEqual(result.duplicate_count, 0)

    def test_different_hn_ids_normalized_url_variants_preserve_both(self):
        result = deduplicate(
            [
                make_discovery("Tool", url="https://example.com/tool", identifiers={"hn_item_id": "111"}),
                make_discovery("Tool", url="https://www.example.com/tool/?utm_source=x", identifiers={"hn_item_id": "222"}),
            ]
        )
        self.assertEqual(result.output_count, 2)
        self.assertEqual(result.duplicate_count, 0)

    def test_no_native_ids_same_source_same_canonical_url_dedups(self):
        result = deduplicate(
            [
                make_discovery("Tool", url="https://example.com/tool"),
                make_discovery("Tool", url="https://www.example.com/tool/?utm_source=x"),
            ]
        )
        self.assertEqual(result.output_count, 1)
        self.assertEqual(
            result.duplicate_groups[0].reason, REASON_CANONICAL_URL_SAME_SOURCE
        )

    def test_one_native_id_one_missing_same_url_documented_contract(self):
        # Documented conservative contract (Step 5.1, case D): the second
        # record carries NO usable native ID, so there is no conflicting
        # second native identity — canonical URL within the same source
        # MAY collapse them. The distinct-ID evidence does not exist.
        result = deduplicate(
            [
                make_discovery("Tool", url="https://example.com/tool", identifiers={"hn_item_id": "111"}),
                make_discovery("Tool", url="https://example.com/tool"),
            ]
        )
        self.assertEqual(result.output_count, 1)
        self.assertEqual(
            result.duplicate_groups[0].reason, REASON_CANONICAL_URL_SAME_SOURCE
        )

    def test_unrelated_namespaces_do_not_create_false_conflict(self):
        # hn_item_id vs reddit_post_id: no SHARED namespace -> no conflict
        # -> same-source canonical URL may dedup.
        result = deduplicate(
            [
                make_discovery("Tool", url="https://example.com/tool", identifiers={"hn_item_id": "111"}),
                make_discovery("Tool", url="https://example.com/tool", identifiers={"reddit_post_id": "abc"}),
            ]
        )
        self.assertEqual(result.output_count, 1)
        self.assertEqual(
            result.duplicate_groups[0].reason, REASON_CANONICAL_URL_SAME_SOURCE
        )

    def test_future_namespace_reddit_post_id_conflict_preserves(self):
        # The rule is source-neutral: differing values in the shared
        # reddit_post_id namespace must also be preserved.
        result = deduplicate(
            [
                make_discovery("Post", url="https://example.com/p", source_name="reddit", identifiers={"reddit_post_id": "a"}),
                make_discovery("Post", url="https://example.com/p", source_name="reddit", identifiers={"reddit_post_id": "b"}),
            ]
        )
        self.assertEqual(result.output_count, 2)
        self.assertEqual(result.duplicate_count, 0)

    def test_conflict_detected_after_collapse_via_merged_identity(self):
        # Record 3 has no ID and collapses into record 1 (URL layer, no
        # conflict). Record 4 carries a DIFFERENT hn_item_id: the merged
        # namespace map (111 from record 1) must trigger the conflict guard
        # so record 4 stays distinct.
        result = deduplicate(
            [
                make_discovery("Tool", url="https://example.com/tool", identifiers={"hn_item_id": "111"}),
                make_discovery("Tool (no id)", url="https://example.com/tool"),
                make_discovery("Tool (other id)", url="https://example.com/tool", identifiers={"hn_item_id": "222"}),
            ]
        )
        self.assertEqual(result.output_count, 2)
        self.assertEqual(result.items[0].title, "Tool")
        self.assertEqual(result.items[1].title, "Tool (other id)")
        self.assertEqual(result.duplicate_groups[0].reason, REASON_CANONICAL_URL_SAME_SOURCE)

    def test_cross_source_behavior_unchanged(self):
        # Same URL, different source_name: still independent provenance.
        result = deduplicate(
            [
                make_discovery("Tool", url="https://example.com/tool", source_name="hacker_news", identifiers={"hn_item_id": "111"}),
                make_discovery("Tool", url="https://example.com/tool", source_name="official_blog"),
            ]
        )
        self.assertEqual(result.output_count, 2)

    def test_stable_order_and_observability_unchanged(self):
        records = [
            make_discovery("A", url="https://example.com/1", identifiers={"hn_item_id": "1"}),
            make_discovery("A dup", url="https://example.com/1?utm_source=x", identifiers={"hn_item_id": "1"}),
            make_discovery("B distinct", url="https://example.com/1", identifiers={"hn_item_id": "2"}),
            make_discovery("C", url="https://example.com/2"),
        ]
        result = deduplicate(records)
        self.assertEqual([item.title for item in result.items], ["A", "B distinct", "C"])
        self.assertEqual(result.input_count, 4)
        self.assertEqual(result.output_count, 3)
        self.assertEqual(result.duplicate_count, 1)
        group = result.duplicate_groups[0]
        self.assertEqual(group.kept_index, 0)
        self.assertEqual(group.removed_indexes, (1,))
        self.assertEqual(group.reason, REASON_NATIVE_IDENTIFIER)
        self.assertEqual(group.identity_key, "hn_item_id=1")


class TestStructuralGuarantees(unittest.TestCase):
    """AST-level guarantees about the dedup module itself."""

    @classmethod
    def _module_tree(cls):
        source = inspect.getsource(deduplicate)
        return ast.parse(source)

    def test_no_fuzzy_matching_libraries(self):
        source = inspect.getsource(deduplicate)
        for forbidden in ("difflib", "SequenceMatcher", "Levenshtein", "rapidfuzz", "embed"):
            self.assertNotIn(forbidden, source)

    def test_no_classification_scoring_ranking_imports(self):
        tree = self._module_tree()
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        self.assertFalse(imported & {"src.research.classify", "src.research.score", "src.research.rank"})
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertNotIn("CandidateScore", names)
        self.assertNotIn("classify", names)

    def test_no_db_network_publishing_imports(self):
        tree = self._module_tree()
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        forbidden = {
            "requests", "urllib", "urllib.request", "socket", "http", "httpx",
            "sqlite3", "subprocess", "os", "pathlib",
            "src.main", "src.storage", "src.factory", "src.agents", "src.integrations",
        }
        self.assertFalse(imported & forbidden)

    def test_no_cluster_priority_dependency(self):
        source = inspect.getsource(deduplicate)
        self.assertNotIn("CLUSTER_PRIORITY", source)

    def test_does_not_construct_discovery_candidate(self):
        tree = self._module_tree()
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertNotIn("DiscoveryCandidate", names)


if __name__ == "__main__":
    unittest.main()
