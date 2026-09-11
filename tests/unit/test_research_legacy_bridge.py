"""Unit tests for the Researcher 2.0 -> legacy news_item bridge (Step 13F)."""

import ast
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.research.legacy_bridge import research_result_to_news_item

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)


def _ranked(candidate_id):
    """Minimal RankedCandidate stand-in: the bridge only reads candidate_id."""
    return SimpleNamespace(candidate_id=candidate_id)


def _candidate(
    candidate_id,
    *,
    title="Weekly AI Digest: Agents Ship Fast",
    url="https://example.com/story",
    published_at=None,
    source_value="github",
):
    """ProcessedCandidate stand-in mirroring the real field structure."""
    return SimpleNamespace(
        candidate_id=candidate_id,
        discovery=SimpleNamespace(
            title=title,
            url=url,
            published_at=published_at,
        ),
        source_type=SimpleNamespace(value=source_value),
    )


def _result(ranked, candidates):
    """ResearchResult stand-in: only .ranked.ranked and .candidates are read."""
    return SimpleNamespace(
        ranked=SimpleNamespace(ranked=tuple(ranked)),
        candidates=tuple(candidates),
    )


class TestShortlistSelection(unittest.TestCase):
    def test_empty_ranked_shortlist_returns_none(self):
        result = _result([], [_candidate("cand_1")])
        self.assertIsNone(research_result_to_news_item(result, now=NOW))

    def test_first_ranked_candidate_selected(self):
        first = _candidate("cand_1", title="First Story")
        second = _candidate("cand_2", title="Second Story")
        result = _result([_ranked("cand_1"), _ranked("cand_2")], [first, second])
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(item["title"], "First Story")

    def test_ranking_order_preserved(self):
        c1 = _candidate("cand_1", title="Alpha")
        c2 = _candidate("cand_2", title="Beta")
        result = _result([_ranked("cand_2"), _ranked("cand_1")], [c1, c2])
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(item["title"], "Beta")


class TestFieldMapping(unittest.TestCase):
    def test_title_maps_from_discovery(self):
        result = _result(
            [_ranked("cand_1")], [_candidate("cand_1", title="Exact Title")]
        )
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(item["title"], "Exact Title")

    def test_source_maps_from_source_type_value(self):
        result = _result(
            [_ranked("cand_1")],
            [_candidate("cand_1", source_value="official_docs")],
        )
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(item["source"], "official_docs")

    def test_url_maps_from_discovery(self):
        result = _result(
            [_ranked("cand_1")],
            [_candidate("cand_1", url="https://example.com/a")],
        )
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(item["url"], "https://example.com/a")

    def test_url_none_becomes_empty_string(self):
        result = _result([_ranked("cand_1")], [_candidate("cand_1", url=None)])
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(item["url"], "")


class TestAgeHours(unittest.TestCase):
    def test_published_at_none_gives_zero_age(self):
        result = _result(
            [_ranked("cand_1")], [_candidate("cand_1", published_at=None)]
        )
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(item["age_hours"], 0)

    def test_naive_now_allowed_when_published_at_missing(self):
        # Rule A/B boundary: awareness is only required when published_at exists.
        result = _result(
            [_ranked("cand_1")], [_candidate("cand_1", published_at=None)]
        )
        naive_now = datetime(2026, 9, 11, 12, 0, 0)
        item = research_result_to_news_item(result, now=naive_now)
        self.assertEqual(item["age_hours"], 0)

    def test_exact_age_calculation(self):
        result = _result(
            [_ranked("cand_1")],
            [_candidate("cand_1", published_at="2026-09-11T06:30:00+00:00")],
        )
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(item["age_hours"], 5.5)

    def test_fractional_age_rounds_to_two_decimals(self):
        # 12:00:00 - 10:39:45 = 1h 20m 15s = 1.3375h -> 1.34
        result = _result(
            [_ranked("cand_1")],
            [_candidate("cand_1", published_at="2026-09-11T10:39:45+00:00")],
        )
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(item["age_hours"], 1.34)

    def test_future_published_at_clamps_to_zero(self):
        result = _result(
            [_ranked("cand_1")],
            [_candidate("cand_1", published_at="2026-09-11T14:00:00+00:00")],
        )
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(item["age_hours"], 0)


class TestErrorContracts(unittest.TestCase):
    def test_naive_now_raises(self):
        result = _result(
            [_ranked("cand_1")],
            [_candidate("cand_1", published_at="2026-09-11T06:30:00+00:00")],
        )
        naive_now = datetime(2026, 9, 11, 12, 0, 0)
        with self.assertRaises(ValueError) as cm:
            research_result_to_news_item(result, now=naive_now)
        self.assertEqual(str(cm.exception), "now must be timezone-aware")

    def test_naive_published_at_raises(self):
        result = _result(
            [_ranked("cand_1")],
            [_candidate("cand_1", published_at="2026-09-11T06:30:00")],
        )
        with self.assertRaises(ValueError) as cm:
            research_result_to_news_item(result, now=NOW)
        self.assertEqual(str(cm.exception), "published_at must be timezone-aware")

    def test_missing_processed_candidate_raises(self):
        result = _result([_ranked("cand_missing")], [_candidate("cand_1")])
        with self.assertRaises(ValueError) as cm:
            research_result_to_news_item(result, now=NOW)
        self.assertEqual(
            str(cm.exception),
            "ranked candidate missing from processed candidates",
        )

    def test_duplicate_processed_candidate_ids_raise(self):
        result = _result(
            [_ranked("cand_1")],
            [_candidate("cand_1", title="A"), _candidate("cand_1", title="B")],
        )
        with self.assertRaises(ValueError) as cm:
            research_result_to_news_item(result, now=NOW)
        self.assertEqual(str(cm.exception), "duplicate processed candidate_id")

    def test_blank_title_raises(self):
        for bad_title in ("", "   ", None, 123):
            with self.subTest(bad_title=bad_title):
                result = _result(
                    [_ranked("cand_1")], [_candidate("cand_1", title=bad_title)]
                )
                with self.assertRaises(ValueError) as cm:
                    research_result_to_news_item(result, now=NOW)
                self.assertEqual(
                    str(cm.exception), "ranked candidate title is empty"
                )


class TestOutputShape(unittest.TestCase):
    def test_output_keys_exact(self):
        result = _result([_ranked("cand_1")], [_candidate("cand_1")])
        item = research_result_to_news_item(result, now=NOW)
        self.assertEqual(set(item), {"title", "source", "url", "age_hours"})

    def test_no_internal_fields_leak(self):
        result = _result([_ranked("cand_1")], [_candidate("cand_1")])
        item = research_result_to_news_item(result, now=NOW)
        for forbidden in (
            "score",
            "cluster",
            "verification",
            "candidate_id",
            "metadata",
            "rank",
            "final_rank_score",
        ):
            self.assertNotIn(forbidden, item)


class TestStructuralBoundaries(unittest.TestCase):
    """AST guarantees: the bridge is a pure mapper with no execution paths."""

    def setUp(self):
        self.source = (
            PROJECT_ROOT / "src" / "research" / "legacy_bridge.py"
        ).read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)
        self.code_text = self._strip_docstrings(self.source, self.tree)

    @staticmethod
    def _strip_docstrings(source, tree):
        docstring_lines = set()
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ) and node.body:
                first = node.body[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    docstring_lines.update(
                        range(first.lineno, first.end_lineno + 1)
                    )
        lines = source.splitlines()
        return "\n".join(
            line
            for idx, line in enumerate(lines, start=1)
            if idx not in docstring_lines
        )

    def test_only_allowed_imports(self):
        modules, names = set(), set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
                names.update(alias.name for alias in node.names)
        self.assertEqual(modules, {"datetime", "src.research.researcher"})
        self.assertEqual(names, {"datetime", "ResearchResult"})

    def test_forbidden_imports_absent(self):
        banned_modules = {
            "src.main",
            "src.agents",
            "requests",
            "urllib",
            "socket",
            "http",
            "yaml",
            "os",
            "dotenv",
            "sqlite3",
            "random",
            "logging",
            "pathlib",
        }
        banned_names = {
            "Researcher",
            "run_live_research",
            "build_live_researcher",
            "Config",
            "StateService",
            "NewsHunter",
            "Strategist",
            "HackerNewsAdapter",
            "GitHubAdapter",
            "OfficialRssAdapter",
        }
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name, banned_modules)
                    self.assertNotIn(alias.name.split(".")[0], banned_modules)
                    self.assertNotIn(alias.asname or alias.name, banned_names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                self.assertNotIn(module, banned_modules)
                self.assertNotIn(module.split(".")[0], banned_modules)
                for alias in node.names:
                    self.assertNotIn(alias.name, banned_names)

    def test_no_forbidden_calls(self):
        banned_name_calls = {
            "open",
            "print",
            "eval",
            "exec",
            "urlopen",
            "rank_candidates",
            "score_candidate",
            "classify",
            "verify_provenance",
            "deduplicate",
            "run_live_research",
            "build_live_researcher",
        }
        banned_attr_calls = {
            "now",
            "utcnow",
            "fetch",
            "safe_fetch",
            "environ",
            "getenv",
        }
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                self.assertNotIn(func.id, banned_name_calls)
            elif isinstance(func, ast.Attribute):
                self.assertNotIn(func.attr, banned_attr_calls)
                if isinstance(func.value, ast.Name):
                    self.assertNotIn(
                        f"{func.value.id}.{func.attr}",
                        {"datetime.now", "datetime.utcnow"},
                    )

    def test_no_hidden_clock_or_env_in_code_text(self):
        for token in (
            "datetime.now",
            "utcnow",
            "os.environ",
            "os.getenv",
            "sqlite3",
            "subprocess",
        ):
            self.assertNotIn(token, self.code_text)


if __name__ == "__main__":
    unittest.main()
