"""Offline end-to-end dry-run harness for Researcher 2.0 (Stage 3.2, Step 12).

Proves the complete pipeline OFFLINE with bundled local fixtures:

    HackerNewsAdapter + GitHubAdapter + OfficialRssAdapter
        -> Researcher.run(now, limit)
        -> dedup -> classify -> verify -> score -> rank

Responsibility boundary:

- READS bundled fixture files under ``tests/fixtures/research_dry_run``;
  WRITES nothing (no filesystem writes anywhere in this module).
- NO network: all three adapters run on injected fakes that serve the
  fixtures. No HTTP library is used by the dry-run path; the adapters'
  production ``requests`` defaults are never touched.
- NO production integration: ``src/main.py``, NewsHunter, Strategist,
  DB/schema/state, ``topic_history.json``, GitHub workflows and config
  files are untouched. The CLI prints a concise human-readable report
  and is diagnostic only.
- NO decisions beyond composition: classification, verification, scoring
  and ranking are the existing Stage 3.2 stage implementations. The
  harness never re-implements a stage, never applies source bonuses,
  and never creates ``StrategicSelection``.

Fixture trust model (deliberately vendor-free): all fixture URLs use
reserved example domains (``example-ai.com``, ``example.net``) and the
fixture trusted domain is ``example-ai.com``, provided through the
curated ``OfficialFeed`` config and merged by the Researcher's existing
trust-combination logic — exactly how production trusted domains would
arrive. No vendor domain is hardcoded anywhere.

Determinism: ``run_offline_dry_run(now=...)`` is a pure function of its
arguments plus the immutable fixture files. ``FIXTURE_NOW_STR`` anchors
the fixture clock (``EPOCH_NOW`` = its Unix epoch, used by the HN
fixtures). Same ``now`` plus same limit -> an identical report.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

from src.domain.strategy import SourceType
from src.research.adapters.github import GitHubAdapter
from src.research.adapters.hacker_news import HackerNewsAdapter
from src.research.adapters.rss import OfficialFeed, OfficialRssAdapter
from src.research.rank import DEFAULT_LIMIT
from src.research.researcher import ResearchResult, Researcher

# ──────────────────────────────────────────────────────────────────────
# Fixture locations and deterministic clock anchor
# ──────────────────────────────────────────────────────────────────────

FIXTURES_DIR = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "research_dry_run"
)

HN_TOPSTORIES_FIXTURE = FIXTURES_DIR / "hn_topstories.json"
HN_ITEMS_FIXTURE = FIXTURES_DIR / "hn_items.json"
GITHUB_SEARCH_FIXTURE = FIXTURES_DIR / "github_search.json"
OFFICIAL_FEED_FIXTURE = FIXTURES_DIR / "official_feed.xml"

#: Fixture clock anchor: 2026-09-11T12:00:00Z. The HN fixtures use Unix
#: epochs computed against this instant (e.g. story 101 at 1789120800
#: = exactly 2 hours older).
EPOCH_NOW: int = 1789128000
FIXTURE_NOW_STR: str = "2026-09-11T12:00:00+00:00"

#: The one curated trusted domain for the dry run (via OfficialFeed).
TRUSTED_DOMAIN: str = "example-ai.com"


# ──────────────────────────────────────────────────────────────────────
# Fixture-backed fetchers (zero network)
# ──────────────────────────────────────────────────────────────────────


class _FixtureHnFetcher:
    """Serves the HN fixtures. No network."""

    def __init__(self) -> None:
        with HN_TOPSTORIES_FIXTURE.open("r", encoding="utf-8") as handle:
            self._story_ids: List[int] = [int(value) for value in json.load(handle)]
        with HN_ITEMS_FIXTURE.open("r", encoding="utf-8") as handle:
            self._items: Dict[str, dict] = json.load(handle)

    def __call__(self, url: str) -> Optional[Any]:
        if url.endswith("topstories.json"):
            return list(self._story_ids)
        parts = urlsplit(url)
        segments = [segment for segment in parts.path.split("/") if segment]
        if len(segments) >= 2 and segments[-2] == "item":
            # Item URLs are "/v0/item/<id>.json"; fixture keys are bare ids.
            return self._items.get(segments[-1].removesuffix(".json"))
        story_id = (parse_qs(parts.query).get("id") or [None])[0]
        if story_id is not None:
            return self._items.get(story_id)
        return None


class _FixtureGitHubFetcher:
    """Serves the GitHub search fixture, routed by the ``q`` query param."""

    def __init__(self) -> None:
        with GITHUB_SEARCH_FIXTURE.open("r", encoding="utf-8") as handle:
            self._payload: Dict[str, Any] = json.load(handle)

    def __call__(self, url: str) -> Optional[Any]:
        query = (parse_qs(urlsplit(url).query).get("q") or [""])[0]
        return self._payload if query else None


def _fixture_fetch_text(url: str) -> Optional[str]:
    """Serves the official feed fixture. No network."""
    host = urlsplit(url).hostname or ""
    if host in ("example-ai.com", "www.example-ai.com"):
        return OFFICIAL_FEED_FIXTURE.read_text(encoding="utf-8")
    return None


def _fixture_hn_now_fn(now: datetime) -> Callable[[], datetime]:
    """Deterministic HN ``now_fn`` — replaces the adapter's hidden clock."""

    def _now() -> datetime:
        return now

    return _now


# ──────────────────────────────────────────────────────────────────────
# Adapter assembly
# ──────────────────────────────────────────────────────────────────────


def build_adapters(
    *,
    now: datetime,
    max_items: int = 50,
    queries: Optional[Tuple[str, ...]] = None,
) -> Tuple[HackerNewsAdapter, GitHubAdapter, OfficialRssAdapter]:
    """Build the three fixture-backed adapters (zero live network)."""
    hn = HackerNewsAdapter(
        fetch_json=_FixtureHnFetcher(),
        now_fn=_fixture_hn_now_fn(now),
        max_items=max_items,
    )
    github = GitHubAdapter(fetch_json=_FixtureGitHubFetcher(), queries=queries)
    rss = OfficialRssAdapter(
        feeds=(
            OfficialFeed(
                name="ExampleAI Blog",
                feed_url="https://example-ai.com/feed.xml",
                trusted_domain=TRUSTED_DOMAIN,
            ),
        ),
        source_type=SourceType.OFFICIAL_BLOG,
        fetch_text=_fixture_fetch_text,
    )
    return hn, github, rss


def fixture_now() -> datetime:
    """The fixture clock anchor as a timezone-aware UTC datetime."""
    return datetime.fromisoformat(FIXTURE_NOW_STR)


# ──────────────────────────────────────────────────────────────────────
# Report model
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RankedSummary:
    """Concise deterministic summary of one ranked shortlist entry."""

    rank: int
    candidate_id: str
    title: str
    url: str
    source_type: str
    cluster: str
    total_score: float
    verification_status: str
    verification_note: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "candidate_id": self.candidate_id,
            "title": self.title,
            "url": self.url,
            "source_type": self.source_type,
            "cluster": self.cluster,
            "total_score": self.total_score,
            "verification_status": self.verification_status,
            "verification_note": self.verification_note,
        }


def _candidate_summaries(
    result: ResearchResult,
) -> Tuple[Dict[str, Any], ...]:
    """Compact per-candidate diagnostics, in deterministic pipeline order.

    One row per processed candidate (ranked or not) so unranked
    candidates stay observable: cluster, verification and scoring
    outcomes are all visible without recomputing any stage.
    """
    summaries: List[Dict[str, Any]] = []
    for item in result.candidates:
        summaries.append(
            {
                "candidate_id": item.candidate_id,
                "title": item.discovery.title,
                "url": item.discovery.url or "",
                "source_type": item.source_type.value,
                "cluster": (
                    item.classification.cluster.value
                    if item.classification.cluster is not None
                    else None
                ),
                "classification_ambiguous": item.classification.ambiguous,
                "verification_status": item.verification.verification_status.value,
                "verification_note": item.verification.notes,
                "verification_confidence": item.verification.confidence,
                "scored": item.score is not None,
                "processing_exclusion": item.processing_exclusion,
            }
        )
    return tuple(summaries)


@dataclass(frozen=True)
class DryRunReport:
    """Concise deterministic diagnostics of one offline dry run.

    Every count is taken straight from the ``ResearchResult``; nothing
    is recomputed or re-decided here. ``to_dict()`` is the stable,
    comparable shape used by the tests.
    """

    now: str
    limit: int
    input_count: int
    deduplicated_count: int
    classified_count: int
    verified_count: int
    scored_count: int
    ranked_count: int
    adapter_outcomes: Tuple[Dict[str, Any], ...]
    ranked_summaries: Tuple[RankedSummary, ...]
    candidate_summaries: Tuple[Dict[str, Any], ...]
    processing_exclusions: Tuple[Dict[str, str], ...]
    trusted_primary_domains: Tuple[str, ...]

    @property
    def stage_counts(self) -> Dict[str, int]:
        return {
            "input_count": self.input_count,
            "deduplicated_count": self.deduplicated_count,
            "classified_count": self.classified_count,
            "verified_count": self.verified_count,
            "scored_count": self.scored_count,
            "ranked_count": self.ranked_count,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "now": self.now,
            "limit": self.limit,
            "counts": self.stage_counts,
            "adapter_outcomes": [dict(outcome) for outcome in self.adapter_outcomes],
            "ranked": [summary.to_dict() for summary in self.ranked_summaries],
            "candidates": [dict(row) for row in self.candidate_summaries],
            "processing_exclusions": [
                dict(exclusion) for exclusion in self.processing_exclusions
            ],
            "trusted_primary_domains": list(self.trusted_primary_domains),
        }


# ──────────────────────────────────────────────────────────────────────
# Dry-run entry points
# ──────────────────────────────────────────────────────────────────────


def run_offline_dry_run(
    *,
    now: datetime,
    limit: int = DEFAULT_LIMIT,
) -> DryRunReport:
    """Run the full Researcher 2.0 pipeline offline over bundled fixtures.

    ``now`` is REQUIRED (no hidden clock). Pure function of ``now``,
    ``limit`` and the immutable fixture files: same inputs -> an
    identical, deeply comparable report.
    """
    hn, github, rss = build_adapters(now=now)
    researcher = Researcher(
        adapters=(hn, github, rss),
        trusted_primary_domains=(),  # trust arrives via the OfficialFeed config
    )
    result: ResearchResult = researcher.run(now=now, limit=limit)

    by_id = {item.candidate_id: item for item in result.candidates}
    ranked_summaries: List[RankedSummary] = []
    for entry in result.ranked.ranked:
        processed = by_id[entry.candidate_id]
        ranked_summaries.append(
            RankedSummary(
                rank=entry.rank,
                candidate_id=entry.candidate_id,
                title=processed.discovery.title,
                url=processed.discovery.url or "",
                source_type=processed.source_type.value,
                cluster=entry.cluster.value,
                total_score=entry.final_rank_score,
                verification_status=processed.verification.verification_status.value,
                verification_note=processed.verification.notes,
            )
        )

    adapter_outcomes = tuple(
        {
            "adapter_name": outcome.adapter_name,
            "source_type": outcome.source_type.value,
            "ok": outcome.ok,
            "record_count": outcome.record_count,
            "error": outcome.error,
        }
        for outcome in result.adapter_results
    )
    candidate_summaries = _candidate_summaries(result)
    exclusions = tuple(
        {"candidate_id": item.candidate_id, "reason": item.processing_exclusion}
        for item in result.candidates
        if item.processing_exclusion is not None
    )

    return DryRunReport(
        now=now.astimezone(timezone.utc).isoformat(),
        limit=limit,
        input_count=result.input_count,
        deduplicated_count=result.deduplicated_count,
        classified_count=result.classified_count,
        verified_count=result.verified_count,
        scored_count=result.scored_count,
        ranked_count=result.ranked.output_count,
        adapter_outcomes=adapter_outcomes,
        ranked_summaries=tuple(ranked_summaries),
        candidate_summaries=candidate_summaries,
        processing_exclusions=exclusions,
        trusted_primary_domains=result.trusted_primary_domains,
    )


def _xml_item_count(path: Path) -> int:
    """Small helper for diagnostics: number of RSS <item> entries."""
    root = ET.parse(path).getroot()
    return sum(1 for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "item")


def format_report(report: DryRunReport) -> str:
    """Concise human-readable, deterministic report text (CLI)."""
    lines: List[str] = []
    lines.append("Researcher 2.0 offline dry run")
    lines.append(f"now: {report.now}  limit: {report.limit}")
    lines.append("")
    lines.append("Adapters:")
    for outcome in report.adapter_outcomes:
        status = "ok" if outcome["ok"] else f"FAILED ({outcome['error']})"
        lines.append(
            f"  - {outcome['adapter_name']} [{outcome['source_type']}]: "
            f"{outcome['record_count']} records, {status}"
        )
    lines.append("")
    lines.append("Stage counts:")
    for name, value in report.stage_counts.items():
        lines.append(f"  {name}: {value}")
    lines.append("")
    lines.append(f"Trusted primary domains: {', '.join(report.trusted_primary_domains)}")
    lines.append("")
    lines.append("Ranked shortlist:")
    if not report.ranked_summaries:
        lines.append("  (empty)")
    for summary in report.ranked_summaries:
        lines.append(
            f"  #{summary.rank} [{summary.cluster}] {summary.total_score:.4f} "
            f"({summary.verification_status}; {summary.verification_note}) "
            f"{summary.source_type}: {summary.title}"
        )
    lines.append("")
    if report.processing_exclusions:
        lines.append("Processing exclusions:")
        for exclusion in report.processing_exclusions:
            lines.append(f"  - {exclusion['candidate_id']}: {exclusion['reason']}")
    else:
        lines.append("Processing exclusions: none")
    return "\n".join(lines)


def main() -> int:
    """CLI entry point: ``python -m src.research.dry_run``.

    Diagnostic only: prints the report, writes nothing, exits 0.
    """
    report = run_offline_dry_run(now=fixture_now())
    print(format_report(report))
    print()
    print(f"fixtures: {FIXTURES_DIR}")
    print(f"official feed <item> entries: {_xml_item_count(OFFICIAL_FEED_FIXTURE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FIXTURES_DIR",
    "EPOCH_NOW",
    "FIXTURE_NOW_STR",
    "TRUSTED_DOMAIN",
    "DryRunReport",
    "RankedSummary",
    "build_adapters",
    "fixture_now",
    "run_offline_dry_run",
    "format_report",
    "main",
]
