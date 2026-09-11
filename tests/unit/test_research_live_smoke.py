"""Unit tests for the live smoke diagnostic module (Step 13E).

Focused tests for exactly the specified behaviors: delegation contracts
of ``run_live_smoke``, error propagation, display-only formatting, and
the structural boundaries of ``live_smoke.py`` (including "the clock
lives ONLY in main()"). unittest + mock only; NO live network, no real
adapters invoked.
"""

from __future__ import annotations

import ast
import sys
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import src.research.live_smoke as live_smoke  # noqa: E402
from src.research.live_smoke import format_live_smoke, run_live_smoke  # noqa: E402

NOW: datetime = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)

LIVE_SMOKE_PY = PROJECT_ROOT / "src" / "research" / "live_smoke.py"


class _Str(str):
    """Plain str carrying the ``.value`` attribute (StrEnum contract)."""

    @property
    def value(self) -> str:
        return str(self)


def _strip_docstrings(tree: ast.AST) -> None:
    """Remove docstrings in place so text scans bind to actual code."""
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


# ──────────────────────────────────────────────────────────────────────
# Minimal fake result objects (mirror the real frozen contracts)
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _FakeDiscovery:
    title: str


@dataclass(frozen=True)
class _FakeVerification:
    verification_status: str


@dataclass(frozen=True)
class _FakeProcessed:
    candidate_id: str
    source_type: str
    verification: _FakeVerification
    discovery: _FakeDiscovery


@dataclass(frozen=True)
class _FakeOutcome:
    adapter_name: str
    source_type: str
    ok: bool
    record_count: int
    error: str = ""


@dataclass(frozen=True)
class _FakeRanked:
    candidate_id: str
    rank: int
    cluster: str
    final_rank_score: float


@dataclass(frozen=True)
class _FakeRanking:
    ranked: tuple
    output_count: int


@dataclass(frozen=True)
class _FakeResult:
    adapter_results: tuple = ()
    input_count: int = 0
    deduplicated_count: int = 0
    classified_count: int = 0
    verified_count: int = 0
    scored_count: int = 0
    ranked: _FakeRanking = field(default_factory=lambda: _FakeRanking((), 0))
    candidates: tuple = ()


def _sample_result() -> _FakeResult:
    candidates = (
        _FakeProcessed(
            "c1", _Str("github"), _FakeVerification(_Str("verified")),
            _FakeDiscovery("owner/repo — code agent"),
        ),
        _FakeProcessed(
            "c2", _Str("hacker_news"), _FakeVerification(_Str("unverified")),
            _FakeDiscovery("Story about AI"),
        ),
    )
    return _FakeResult(
        adapter_results=(
            _FakeOutcome("hacker_news", _Str("hacker_news"), True, 12),
            _FakeOutcome("github", _Str("github"), True, 3),
            _FakeOutcome("official_rss", _Str("official_blog"), True, 2),
            _FakeOutcome("official_rss", _Str("official_docs"), False, 0, "RSSFetchError: boom"),
        ),
        input_count=17,
        deduplicated_count=15,
        classified_count=15,
        verified_count=15,
        scored_count=14,
        ranked=_FakeRanking(
            (
                _FakeRanked("c1", 1, _Str("vibe_coding"), 6.125),
                _FakeRanked("c2", 2, _Str("ai_news"), 5.5),
            ),
            2,
        ),
        candidates=candidates,
    )


class TestRunLiveSmoke(unittest.TestCase):
    """Delegation contracts of run_live_smoke (spec 1-9)."""

    def _run_patched(self, result=None, config_error=None, run_error=None):
        """Patch Config.get_research_config and live.run_live_research."""
        fake_config = mock.Mock()
        fake_config.live_kwargs.return_value = {
            "blog_feeds": ("FEED-BLOG",),
            "docs_feeds": ("FEED-DOCS",),
            "trusted_primary_domains": ("github.blog",),
        }
        if config_error is not None:
            fake_config_method = mock.Mock(side_effect=config_error)
        else:
            fake_config_method = mock.Mock(return_value=fake_config)

        fake_run = (
            mock.Mock(side_effect=run_error)
            if run_error is not None
            else mock.Mock(return_value=result if result is not None else mock.sentinel.RESULT)
        )

        with mock.patch.object(
            live_smoke.Config, "get_research_config", fake_config_method
        ), mock.patch.object(live_smoke, "run_live_research", fake_run):
            returned = run_live_smoke(now=NOW, limit=3)

        return fake_config_method, fake_config, fake_run, returned

    def test_calls_get_research_config_exactly_once(self) -> None:
        config_method, _, _, _ = self._run_patched()
        self.assertEqual(config_method.call_count, 1)

    def test_calls_live_kwargs_exactly_once(self) -> None:
        _, fake_config, _, _ = self._run_patched()
        fake_config.live_kwargs.assert_called_once_with()

    def test_calls_run_live_research_exactly_once(self) -> None:
        _, _, fake_run, _ = self._run_patched()
        self.assertEqual(fake_run.call_count, 1)

    def test_exact_now_forwarded(self) -> None:
        _, _, fake_run, _ = self._run_patched()
        self.assertIs(fake_run.call_args.kwargs["now"], NOW)

    def test_exact_limit_forwarded(self) -> None:
        _, _, fake_run, _ = self._run_patched()
        self.assertEqual(fake_run.call_args.kwargs["limit"], 3)

    def test_exact_live_kwargs_forwarded(self) -> None:
        _, _, fake_run, _ = self._run_patched()
        kwargs = fake_run.call_args.kwargs
        self.assertEqual(kwargs["blog_feeds"], ("FEED-BLOG",))
        self.assertEqual(kwargs["docs_feeds"], ("FEED-DOCS",))
        self.assertEqual(kwargs["trusted_primary_domains"], ("github.blog",))

    def test_result_returned_unchanged_by_identity(self) -> None:
        marker = mock.sentinel.RESULT
        _, _, _, returned = self._run_patched(result=marker)
        self.assertIs(returned, marker)

    def test_exception_from_get_research_config_propagates(self) -> None:
        with self.assertRaises(RuntimeError):
            self._run_patched(config_error=RuntimeError("config boom"))

    def test_exception_from_run_live_research_propagates(self) -> None:
        with self.assertRaises(RuntimeError):
            self._run_patched(run_error=RuntimeError("run boom"))


class TestFormatLiveSmoke(unittest.TestCase):
    """Display-only formatter (spec 10-14)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = format_live_smoke(_sample_result())

    def test_includes_all_adapter_outcomes(self) -> None:
        self.assertIn("hacker_news [hacker_news]: 12 records, ok", self.text)
        self.assertIn("github [github]: 3 records, ok", self.text)
        self.assertIn("official_rss [official_blog]: 2 records, ok", self.text)
        # error only when present
        self.assertIn(
            "official_rss [official_docs]: 0 records, FAILED (RSSFetchError: boom)",
            self.text,
        )
        self.assertIn("Adapters:", self.text)

    def test_includes_exact_pipeline_counts(self) -> None:
        self.assertIn("Counts:", self.text)
        self.assertIn("input=17", self.text)
        self.assertIn("deduplicated=15", self.text)
        self.assertIn("classified=15", self.text)
        self.assertIn("verified=15", self.text)
        self.assertIn("scored=14", self.text)
        self.assertIn("ranked=2", self.text)

    def test_includes_ranked_candidate_details(self) -> None:
        self.assertIn("Ranked:", self.text)
        self.assertIn(
            "#1 [vibe_coding] 6.1250 github verified | owner/repo — code agent",
            self.text,
        )
        self.assertIn(
            "#2 [ai_news] 5.5000 hacker_news unverified | Story about AI",
            self.text,
        )

    def test_empty_ranked_shortlist_prints_empty(self) -> None:
        empty = _FakeResult(
            adapter_results=(_FakeOutcome("github", _Str("github"), True, 0),),
            ranked=_FakeRanking((), 0),
            candidates=(),
        )
        text = format_live_smoke(empty)
        self.assertIn("(empty)", text)
        self.assertIn("ranked=0", text)

    def test_formatter_does_not_call_stage_functions(self) -> None:
        # The formatter takes an inert dataclass result; this test pins
        # that formatting performs no stage calls by re-running it under
        # guards: if any stage function were called, it would need the
        # real modules; patch them to explode if touched.
        with mock.patch("src.research.live_smoke.run_live_research") as run_m, mock.patch.object(
            live_smoke.Config, "get_research_config"
        ) as cfg_m:
            format_live_smoke(_sample_result())
            run_m.assert_not_called()
            cfg_m.assert_not_called()


class TestStructuralBoundaries(unittest.TestCase):
    """AST guarantees on live_smoke.py (spec 15-16)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = LIVE_SMOKE_PY.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        _strip_docstrings(cls.tree)

    def _function(self, name: str) -> ast.FunctionDef:
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
        raise AssertionError(f"function not found: {name}")

    def test_no_forbidden_imports(self) -> None:
        imported: set = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for forbidden in (
            "src.main",
            "requests",
            "yaml",
            "os",
            "dotenv",
            "sqlite3",
            "logging",
        ):
            self.assertNotIn(forbidden, imported)
        for module in imported:
            self.assertFalse(
                module.startswith(("src.agents", "src.factory", "src.storage", "src.state")),
                f"forbidden import: {module}",
            )

    def test_no_forbidden_names_in_code(self) -> None:
        code_text = ast.unparse(self.tree)
        for forbidden in (
            "os.environ",
            "os.getenv",
            "StrategicSelection",
            "ContentItem",
            "sqlite3",
        ):
            self.assertNotIn(forbidden, code_text)
        # print() is allowed ONLY inside main() (diagnostic CLI contract).
        for name in ("run_live_smoke", "format_live_smoke"):
            self.assertNotIn("print(", ast.unparse(self._function(name)))
        self.assertIn("print(", ast.unparse(self._function("main")))

    def test_datetime_now_only_inside_main(self) -> None:
        for name in ("run_live_smoke", "format_live_smoke"):
            func_text = ast.unparse(self._function(name))
            self.assertNotIn("datetime.now", func_text)
            self.assertNotIn("utcnow", func_text)
        main_text = ast.unparse(self._function("main"))
        self.assertIn("datetime.now", main_text)

    def test_run_live_smoke_does_not_construct_adapters(self) -> None:
        func_text = ast.unparse(self._function("run_live_smoke"))
        for forbidden in (
            "HackerNewsAdapter",
            "GitHubAdapter",
            "OfficialRssAdapter",
            "safe_fetch",
            ".fetch(",
        ):
            self.assertNotIn(forbidden, func_text)

    def test_main_contract(self) -> None:
        main_func = self._function("main")
        main_text = ast.unparse(main_func)
        self.assertIn("datetime.now(timezone.utc)", main_text)
        self.assertIn("SMOKE_LIMIT", main_text)
        self.assertIn("return 0", main_text)


if __name__ == "__main__":
    unittest.main()
