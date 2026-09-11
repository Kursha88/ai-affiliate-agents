"""Live Researcher 2.0 smoke run (Stage 3.2, Step 13E).

DIAGNOSTIC ONLY. Runs the REAL Researcher 2.0 against the currently
configured live sources and prints a concise report. It must NOT
publish, generate content, modify DB/state/files, or alter the
production pipeline or configuration.

Composition (nothing re-implemented here):

    Config.get_research_config()          (existing loader, Step 13C)
        -> LiveResearchConfig.live_kwargs()
        -> run_live_research(now, limit, **kwargs)   (Step 13A wiring)
        -> ResearchResult returned unchanged

Boundaries:

- ``run_live_smoke`` performs no exception catching, no fallback
  results, no transformation, no direct network logic, no direct
  adapter construction. Live HTTP happens ONLY indirectly through
  ``run_live_research()`` -> existing wiring -> existing adapters.
- ``format_live_smoke`` only DISPLAYS existing result fields; it never
  recomputes scores, ranks, classifications or verifications.
- The current clock is used ONLY inside ``main()`` because this file is
  a diagnostic CLI; ``run_live_smoke`` itself uses only its injected
  ``now``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from src.core.config import Config
from src.research.live import run_live_research
from src.research.researcher import ResearchResult

#: Conservative default shortlist size for a smoke run.
SMOKE_LIMIT: int = 5

__all__ = ["SMOKE_LIMIT", "run_live_smoke", "format_live_smoke", "main"]


def run_live_smoke(
    *,
    now: datetime,
    limit: int = SMOKE_LIMIT,
) -> ResearchResult:
    """Run the real Researcher with the currently configured sources.

    ``now`` is REQUIRED (no hidden clock in this function — the only
    clock in this module lives in ``main()``). The ``ResearchResult``
    is returned unchanged: no catching, no fallback, no transformation.
    """
    config = Config.get_research_config()
    return run_live_research(
        now=now,
        limit=limit,
        **config.live_kwargs(),
    )


def format_live_smoke(result: ResearchResult) -> str:
    """Concise human-readable smoke report (display only)."""
    lines: List[str] = []

    lines.append("Researcher 2.0 LIVE smoke")
    lines.append("")
    lines.append("Adapters:")
    for outcome in result.adapter_results:
        status = "ok" if outcome.ok else f"FAILED ({outcome.error})"
        lines.append(
            f"  - {outcome.adapter_name} [{outcome.source_type.value}]: "
            f"{outcome.record_count} records, {status}"
        )
    lines.append("")
    lines.append("Counts:")
    lines.append(f"  input={result.input_count}")
    lines.append(f"  deduplicated={result.deduplicated_count}")
    lines.append(f"  classified={result.classified_count}")
    lines.append(f"  verified={result.verified_count}")
    lines.append(f"  scored={result.scored_count}")
    lines.append(f"  ranked={result.ranked.output_count}")
    lines.append("")
    lines.append("Ranked:")

    by_id: Dict[str, object] = {
        item.candidate_id: item for item in result.candidates
    }
    ranked_entries = list(result.ranked.ranked)
    if not ranked_entries:
        lines.append("(empty)")
    for entry in ranked_entries:
        processed = by_id[entry.candidate_id]
        lines.append(
            f"  #{entry.rank} [{entry.cluster.value}] "
            f"{entry.final_rank_score:.4f} "
            f"{processed.source_type.value} "
            f"{processed.verification.verification_status.value} | "
            f"{processed.discovery.title}"
        )
    return "\n".join(lines)


def main() -> int:
    """CLI entry point: ``python -m src.research.live_smoke``.

    The ONLY place in this module allowed to read the current clock.
    Diagnostic only: prints the report, writes nothing, exits 0.
    """
    now = datetime.now(timezone.utc)
    result = run_live_smoke(now=now, limit=SMOKE_LIMIT)
    print(format_live_smoke(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
