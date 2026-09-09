"""Unit tests for the GitHub discovery adapter (Stage 3.2, Step 9).

Covers the required matrix: name/source_type, normal repository
mapping (stars -> raw_score, github_stars label, identifiers,
description -> summary, neutral license metadata), conservative
skipping (archived, forks, malformed payload, missing id, missing
full_name, invalid URL, non-public), multi-query discovery with
native-identity dedup (numeric repo id strongest, owner/repo fallback,
similar names preserved), matched_queries merging, limits
(per_query_limit, max_results, invalid values), failure isolation
(one query fails, partial success, all-fail -> safe_fetch failure),
determinism, purity (no input mutation, no live network), and
structural guarantees (no classification/verification/scoring/ranking
imports, no DB/publishing imports, no environment reads in business
logic).

All fetches go through injected fakes; ZERO live network.
"""

from __future__ import annotations

import ast
import copy
import inspect
import unittest
from typing import Any, Dict, List, Optional

from src.domain.strategy import SourceType
from src.research.adapters.base import SourceAdapter
from src.research.adapters.github import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_PER_QUERY_LIMIT,
    DEFAULT_SEARCH_QUERIES,
    GITHUB_API_BASE,
    GitHubAdapter,
    GitHubFetchError,
)


def repo_payload(
    repo_id: int,
    full_name: str,
    *,
    description: str = "A useful AI tool",
    stars: int = 42,
    forks_count: int = 7,
    watchers_count: int = 9,
    open_issues_count: int = 3,
    language: str = "Python",
    topics: Optional[List[str]] = None,
    license_key: str = "mit",
    license_name: str = "MIT License",
    archived: bool = False,
    fork: bool = False,
    html_url: Optional[str] = "unset",
    pushed_at: str = "2026-09-08T10:00:00Z",
    updated_at: str = "2026-09-08T11:00:00Z",
    created_at: str = "2026-01-01T00:00:00Z",
    default_branch: str = "main",
    homepage: str = "https://example.dev",
    visibility: str = "public",
) -> Dict[str, Any]:
    return {
        "id": repo_id,
        "full_name": full_name,
        "name": full_name.split("/")[-1],
        "description": description,
        "html_url": html_url or f"https://github.com/{full_name}",
        "stargazers_count": stars,
        "forks_count": forks_count,
        "watchers_count": watchers_count,
        "open_issues_count": open_issues_count,
        "language": language,
        "topics": topics if topics is not None else ["ai", "agents"],
        "license": {"key": license_key, "name": license_name},
        "archived": archived,
        "fork": fork,
        # "unset" sentinel -> default; ""/None pass through as invalid.
        "html_url": (f"https://github.com/{full_name}" if html_url == "unset" else html_url),
        "pushed_at": pushed_at,
        "updated_at": updated_at,
        "created_at": created_at,
        "default_branch": default_branch,
        "homepage": homepage,
        "visibility": visibility,
    }


def make_fetcher(
    responses: Dict[str, Any],
    *,
    calls: Optional[List[str]] = None,
) -> Any:
    """Injectable fetch_json: URL -> payload (or None)."""

    def fetch_json(url: str) -> Optional[Any]:
        if calls is not None:
            calls.append(url)
        return responses.get(url)

    return fetch_json


def search_url(query: str, per_page: int = DEFAULT_PER_QUERY_LIMIT) -> str:
    from urllib.parse import quote_plus

    return f"{GITHUB_API_BASE}/search/repositories?q={quote_plus(query)}&per_page={per_page}"


def items_payload(*repos: Dict[str, Any]) -> Dict[str, Any]:
    return {"items": list(repos)}


def make_adapter(
    responses: Dict[str, Any],
    *,
    calls: Optional[List[str]] = None,
    queries: Optional[tuple[str, ...]] = None,
    **kwargs: Any,
) -> GitHubAdapter:
    return GitHubAdapter(
        fetch_json=make_fetcher(responses, calls=calls),
        queries=queries,
        **kwargs,
    )


# ══════════════════════════════════════════════════════════════════════
# Contract and mapping
# ══════════════════════════════════════════════════════════════════════


class TestAdapterContract(unittest.TestCase):
    def test_name_and_source_type(self):
        adapter = make_adapter({})
        self.assertEqual(adapter.name, "github")
        self.assertEqual(adapter.source_type, SourceType.GITHUB)
        self.assertIsInstance(adapter, SourceAdapter)

    def test_multiple_default_queries_used(self):
        calls: List[str] = []
        adapter = make_adapter({}, calls=calls)
        with self.assertRaises(GitHubFetchError):
            adapter.fetch()
        self.assertEqual(len(calls), len(DEFAULT_SEARCH_QUERIES))
        self.assertEqual(adapter.last_fetch_stats["requested_queries"], len(DEFAULT_SEARCH_QUERIES))
        for query in DEFAULT_SEARCH_QUERIES:
            self.assertIn(search_url(query), calls)
            # Multi-word queries must be URL-encoded (no raw spaces).
            q_param = search_url(query).split("q=")[1].split("&")[0]
            self.assertNotIn(" ", q_param)


class TestNormalMapping(unittest.TestCase):
    def _single_query_adapter(self, repo: Dict[str, Any]) -> GitHubAdapter:
        return make_adapter(
            {search_url("q1"): items_payload(repo)},
            queries=("q1",),
        )

    def test_normal_repository_mapping(self):
        repo = repo_payload(101, "owner/tool")
        result = make_adapter({search_url("q1"): items_payload(repo)}, queries=("q1",)).fetch()
        self.assertEqual(len(result), 1)
        record = result[0]
        self.assertEqual(record.title, "owner/tool: A useful AI tool")
        self.assertEqual(record.url, "https://github.com/owner/tool")
        self.assertEqual(record.source_name, "github")
        self.assertEqual(record.summary, "A useful AI tool")

    def test_stars_become_raw_score_with_label(self):
        repo = repo_payload(101, "owner/tool", stars=1234)
        record = self._single_query_adapter(repo).fetch()[0]
        self.assertEqual(record.raw_score, 1234.0)
        self.assertEqual(record.raw_score_label, "github_stars")

    def test_identifiers(self):
        repo = repo_payload(101, "Owner/Tool")
        record = self._single_query_adapter(repo).fetch()[0]
        self.assertEqual(record.identifiers["github_repo"], "owner/tool")
        self.assertEqual(record.identifiers["github_repo_id"], "101")

    def test_description_becomes_summary(self):
        repo = repo_payload(101, "owner/tool", description="  Does agentic things. Fast.  ")
        record = self._single_query_adapter(repo).fetch()[0]
        self.assertEqual(record.summary, "Does agentic things. Fast.")
        self.assertTrue(record.title.startswith("owner/tool: Does agentic things"))

    def test_missing_description_yields_plain_title_and_empty_summary(self):
        repo = repo_payload(101, "owner/tool", description=None)
        record = self._single_query_adapter(repo).fetch()[0]
        self.assertEqual(record.title, "owner/tool")
        self.assertEqual(record.summary, "")

    def test_license_retained_only_as_metadata(self):
        repo = repo_payload(101, "owner/tool", license_key="apache-2.0", license_name="Apache License 2.0")
        record = self._single_query_adapter(repo).fetch()[0]
        self.assertEqual(record.metadata["license_key"], "apache-2.0")
        self.assertEqual(record.metadata["license_name"], "Apache License 2.0")
        # Neutral metadata must not leak into the discovery identity fields.
        for field in (record.title, record.summary, record.url):
            self.assertNotIn("apache", str(field).lower())

    def test_github_source_does_not_mark_repo_free_or_open(self):
        repo = repo_payload(
            101, "owner/tool",
            license_key="mit", license_name="MIT License",
            topics=["open-source", "free"],
        )
        record = self._single_query_adapter(repo).fetch()[0]
        # No free/open inference: no scoring fields, no cluster, no flags.
        self.assertNotIn("free", record.metadata)
        self.assertNotIn("open_source", record.metadata)
        self.assertNotIn("is_open_source", record.metadata)
        self.assertFalse(hasattr(record, "cluster"))
        # metadata retains license/topics as neutral provenance only.
        self.assertEqual(record.metadata["license_key"], "mit")

    def test_metadata_provenance_retained(self):
        repo = repo_payload(101, "owner/tool")
        record = self._single_query_adapter(repo).fetch()[0]
        for key in (
            "owner", "repo_name", "full_name", "stars", "forks", "watchers",
            "open_issues_count", "language", "topics", "archived", "fork",
            "pushed_at", "updated_at", "created_at", "default_branch",
            "homepage", "visibility", "discovery_query", "matched_queries",
        ):
            self.assertIn(key, record.metadata, key)
        self.assertEqual(record.metadata["pushed_at"], "2026-09-08T10:00:00+00:00")
        self.assertEqual(record.metadata["discovery_query"], "q1")
        self.assertEqual(record.metadata["matched_queries"], ("q1",))

    def test_published_at_prefers_pushed_at(self):
        record = self._single_query_adapter(repo_payload(101, "owner/tool")).fetch()[0]
        self.assertEqual(record.published_at, "2026-09-08T10:00:00+00:00")

    def test_published_at_falls_back_to_updated_at(self):
        repo = repo_payload(101, "owner/tool", pushed_at=None)
        record = self._single_query_adapter(repo).fetch()[0]
        self.assertEqual(record.published_at, "2026-09-08T11:00:00+00:00")

    def test_comments_count_is_none(self):
        repo = repo_payload(101, "owner/tool", forks_count=50, open_issues_count=30)
        record = self._single_query_adapter(repo).fetch()[0]
        self.assertIsNone(record.comments_count)

    def test_no_datetime_now_calls(self):
        # TIME rule: timestamps come from the source only. Docstrings are
        # stripped (the module legitimately documents the prohibition).
        from src.research.adapters import github as github_module

        tree = ast.parse(inspect.getsource(github_module))
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


# ══════════════════════════════════════════════════════════════════════
# Conservative filtering
# ══════════════════════════════════════════════════════════════════════


class TestFiltering(unittest.TestCase):
    def _fetch_one(self, repo: Any) -> List[Any]:
        adapter = make_adapter({search_url("q1"): items_payload(repo)}, queries=("q1",))
        return adapter.fetch()

    def assert_skipped(self, repo: Any, reason: str) -> None:
        adapter = make_adapter({search_url("q1"): items_payload(repo)}, queries=("q1",))
        self.assertEqual(adapter.fetch(), [])
        self.assertEqual(adapter.last_fetch_stats["skipped"].get(reason), 1)

    def test_archived_skipped(self):
        self.assert_skipped(repo_payload(101, "owner/tool", archived=True), "archived")

    def test_forks_skipped(self):
        self.assert_skipped(repo_payload(101, "owner/tool", fork=True), "fork")

    def test_malformed_payload_skipped(self):
        self.assert_skipped("not-a-dict", "malformed_payload")
        self.assert_skipped(None, "malformed_payload")

    def test_missing_id_skipped(self):
        repo = repo_payload(101, "owner/tool")
        del repo["id"]
        self.assert_skipped(repo, "missing_repo_id")

    def test_non_positive_id_skipped(self):
        self.assert_skipped(repo_payload(0, "owner/tool"), "missing_repo_id")
        self.assert_skipped(repo_payload(True, "owner/tool"), "missing_repo_id")

    def test_missing_full_name_skipped(self):
        repo = repo_payload(101, "owner/tool")
        del repo["full_name"]
        self.assert_skipped(repo, "missing_full_name")
        self.assert_skipped(repo_payload(102, ""), "missing_full_name")
        self.assert_skipped(repo_payload(103, "just-a-name"), "missing_full_name")

    def test_invalid_url_skipped(self):
        self.assert_skipped(repo_payload(101, "owner/tool", html_url=""), "missing_or_invalid_url")
        self.assert_skipped(repo_payload(102, "owner/tool", html_url="https://evil.example/owner/tool"),
                            "missing_or_invalid_url")
        repo = repo_payload(103, "owner/tool")
        del repo["html_url"]
        self.assert_skipped(repo, "missing_or_invalid_url")

    def test_non_public_skipped(self):
        self.assert_skipped(repo_payload(101, "owner/tool", visibility="private"), "non_public")

    def test_no_star_threshold_filtering(self):
        adapter = make_adapter(
            {search_url("q1"): items_payload(repo_payload(101, "owner/tool", stars=0))},
            queries=("q1",),
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].raw_score, 0.0)
        self.assertNotIn("low_stars", adapter.last_fetch_stats["skipped"])

    def test_no_ai_keyword_filtering(self):
        adapter = make_adapter(
            {search_url("q1"): items_payload(repo_payload(101, "owner/robot-vacuum"))},
            queries=("q1",),
        )
        self.assertEqual(len(adapter.fetch()), 1)


# ══════════════════════════════════════════════════════════════════════
# Dedup and limits
# ══════════════════════════════════════════════════════════════════════


class TestDedupAndLimits(unittest.TestCase):
    def test_duplicate_repo_across_queries_dedups(self):
        repo = repo_payload(101, "owner/tool")
        adapter = make_adapter(
            {
                search_url("q1"): items_payload(repo),
                search_url("q2"): items_payload(repo),
            },
            queries=("q1", "q2"),
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(adapter.last_fetch_stats["kept"], 1)

    def test_matched_queries_merged(self):
        repo = repo_payload(101, "owner/tool")
        result = make_adapter(
            {
                search_url("q1"): items_payload(repo),
                search_url("q2"): items_payload(repo_payload(101, "owner/tool")),
            },
            queries=("q1", "q2"),
        ).fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].metadata["matched_queries"], ("q1", "q2"))
        self.assertEqual(result[0].metadata["discovery_query"], "q1")

    def test_numeric_repo_id_is_strongest_identity(self):
        # Same numeric id, different owner/repo strings: one repository.
        result = make_adapter(
            {
                search_url("q1"): items_payload(repo_payload(101, "owner/tool")),
                search_url("q2"): items_payload(repo_payload(101, "other/name")),
            },
            queries=("q1", "q2"),
        ).fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].identifiers["github_repo_id"], "101")

    def test_owner_repo_fallback_dedup(self):
        # Different numeric ids but the same owner/repo: one repository
        # by explicit owner/repo identity (defensive fallback).
        result = make_adapter(
            {
                search_url("q1"): items_payload(repo_payload(101, "owner/tool")),
                search_url("q2"): items_payload(repo_payload(202, "owner/tool")),
            },
            queries=("q1", "q2"),
        ).fetch()
        self.assertEqual(len(result), 1)

    def test_different_repos_with_similar_names_preserved(self):
        result = make_adapter(
            {
                search_url("q1"): items_payload(
                    repo_payload(101, "owner/tool"),
                    repo_payload(102, "owner/toolkit"),
                    repo_payload(103, "owner/tool-ai"),
                ),
            },
            queries=("q1",),
        ).fetch()
        self.assertEqual(len(result), 3)
        self.assertEqual(
            {r.identifiers["github_repo"] for r in result},
            {"owner/tool", "owner/toolkit", "owner/tool-ai"},
        )

    def test_no_fuzzy_title_dedup(self):
        result = make_adapter(
            {
                search_url("q1"): items_payload(
                    repo_payload(101, "owner/ai-agent-framework"),
                    repo_payload(102, "other/ai-agent-framework"),
                ),
            },
            queries=("q1",),
        ).fetch()
        self.assertEqual(len(result), 2)

    def test_per_query_limit_enforced(self):
        many = [repo_payload(1000 + i, f"owner/repo{i}") for i in range(30)]
        adapter = make_adapter(
            {search_url("q1", per_page=5): items_payload(*many)},
            queries=("q1",),
            per_query_limit=5,
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 5)
        self.assertEqual(adapter.last_fetch_stats["parsed"], 5)

    def test_max_results_enforced(self):
        repos = [repo_payload(1000 + i, f"owner/repo{i}") for i in range(10)]
        adapter = make_adapter(
            {
                search_url("q1"): items_payload(*repos[:5]),
                search_url("q2"): items_payload(*repos[5:]),
            },
            queries=("q1", "q2"),
            max_results=7,
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 7)
        self.assertEqual(adapter.last_fetch_stats["kept"], 7)

    def test_invalid_limits_raise_valueerror(self):
        responses: Dict[str, Any] = {}
        for value in (0, -5, 1.5, "10", None, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    GitHubAdapter(
                        fetch_json=make_fetcher(responses),
                        per_query_limit=value,
                    )
                with self.assertRaises(ValueError):
                    GitHubAdapter(
                        fetch_json=make_fetcher(responses),
                        max_results=value,
                    )

    def test_conservative_defaults(self):
        self.assertEqual(DEFAULT_PER_QUERY_LIMIT, 20)
        self.assertEqual(DEFAULT_MAX_RESULTS, 50)


# ══════════════════════════════════════════════════════════════════════
# Failure isolation
# ══════════════════════════════════════════════════════════════════════


class TestFailureIsolation(unittest.TestCase):
    def test_one_query_failure_isolated(self):
        good = repo_payload(101, "owner/tool")
        adapter = make_adapter(
            {
                search_url("q1"): None,  # fetch failed
                search_url("q2"): items_payload(good),
            },
            queries=("q1", "q2"),
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 1)
        stats = adapter.last_fetch_stats
        self.assertEqual(stats["failed_queries"], 1)
        self.assertEqual(stats["query_errors"]["q1"], "fetch_failed")
        self.assertEqual(stats["kept"], 1)

    def test_malformed_search_payload_is_query_failure(self):
        good = repo_payload(101, "owner/tool")
        adapter = make_adapter(
            {
                search_url("q1"): {"unexpected": "shape"},
                search_url("q2"): items_payload(good),
            },
            queries=("q1", "q2"),
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(adapter.last_fetch_stats["query_errors"]["q1"], "malformed_search_payload")

    def test_partial_success_returns_discoveries_and_stats(self):
        adapter = make_adapter(
            {
                search_url("q1"): None,
                search_url("q2"): items_payload(repo_payload(201, "owner/a")),
                search_url("q3"): items_payload(repo_payload(202, "owner/b")),
            },
            queries=("q1", "q2", "q3"),
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 2)
        self.assertEqual(adapter.last_fetch_stats["failed_queries"], 1)
        self.assertEqual(adapter.last_fetch_stats["kept"], 2)

    def test_all_query_failure_becomes_safe_fetch_failure(self):
        adapter = make_adapter(
            {search_url(q): None for q in ("q1", "q2")},
            queries=("q1", "q2"),
        )
        with self.assertRaises(GitHubFetchError):
            adapter.fetch()
        discoveries = adapter.safe_fetch()
        self.assertEqual(discoveries, [])
        self.assertIsNotNone(adapter.last_error)
        self.assertIn("GitHubFetchError", adapter.last_error)

    def test_no_silent_swallow_of_malformed_items(self):
        # Malformed items are skipped but counted, never silent.
        adapter = make_adapter(
            {
                search_url("q1"): items_payload(
                    repo_payload(101, "owner/tool"),
                    "garbage",
                    repo_payload(102, "owner/other"),
                ),
            },
            queries=("q1",),
        )
        result = adapter.fetch()
        self.assertEqual(len(result), 2)
        self.assertEqual(adapter.last_fetch_stats["skipped"].get("malformed_payload"), 1)
        self.assertEqual(adapter.last_fetch_stats["parsed"], 2)


# ══════════════════════════════════════════════════════════════════════
# Determinism, purity, structure
# ══════════════════════════════════════════════════════════════════════


class TestDeterminismPurityStructure(unittest.TestCase):
    def _responses(self) -> Dict[str, Any]:
        return {
            search_url("q1"): items_payload(
                repo_payload(101, "owner/tool"),
                repo_payload(102, "owner/agent"),
            ),
            search_url("q2"): items_payload(
                repo_payload(101, "owner/tool"),
                repo_payload(103, "owner/other"),
            ),
        }

    def test_deterministic_output(self):
        first = make_adapter(self._responses(), queries=("q1", "q2")).fetch()
        second = make_adapter(self._responses(), queries=("q1", "q2")).fetch()
        self.assertEqual(first, second)
        self.assertEqual(
            [r.identifiers["github_repo"] for r in first],
            ["owner/tool", "owner/agent", "owner/other"],
        )

    def test_raw_discovery_fields_not_mutated(self):
        import copy as copy_module

        from src.research.adapters.base import RawDiscovery

        record = GitHubAdapter(
            fetch_json=make_fetcher(self._responses()), queries=("q1", "q2")
        ).fetch()[0]
        snapshot = copy_module.deepcopy(record)
        self.assertIsInstance(record, RawDiscovery)
        with self.assertRaises((AttributeError, TypeError)):
            record.title = "mutated"  # type: ignore[misc]
        self.assertEqual(record, snapshot)

    def test_no_live_network_required(self):
        # The entire suite runs on injected fakes; assert the production
        # default is lazy (not invoked at import/construction time).
        calls: List[str] = []
        adapter = make_adapter(self._responses(), queries=("q1", "q2"), calls=calls)
        self.assertEqual(calls, [])  # nothing fetched before fetch()
        adapter.fetch()
        self.assertTrue(all(url.startswith(GITHUB_API_BASE) for url in calls))

    def test_no_classification_verification_scoring_ranking_imports(self):
        from src.research.adapters import github as github_module

        tree = ast.parse(inspect.getsource(github_module))
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
        # ``requests`` is allowed ONLY as the lazy production client
        # inside default_fetch_json (same pattern as the HN adapter) —
        # never at module level, never in business logic.
        lazy_nodes = {
            id(node)
            for fn in ast.walk(tree)
            if isinstance(fn, ast.FunctionDef) and fn.name == "default_fetch_json"
            for node in ast.walk(fn)
            if isinstance(node, ast.Import)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == "requests" for alias in node.names
            ):
                self.assertIn(id(node), lazy_nodes, "requests import must be lazy")
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for forbidden in (
            "classify", "verify_provenance", "score_candidate",
            "rank_candidates", "CandidateScore", "VerificationResult",
            "ClassificationResult", "StrategicSelection",
        ):
            self.assertNotIn(forbidden, names)

    def test_no_environment_reads_in_business_logic(self):
        from src.research.adapters import github as github_module

        tree = ast.parse(inspect.getsource(github_module))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertNotIn("environ", names)
        self.assertNotIn("getenv", names)


if __name__ == "__main__":
    unittest.main()
