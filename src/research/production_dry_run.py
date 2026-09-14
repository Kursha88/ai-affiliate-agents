"""Live end-to-end production dry run (Stage 3.2, Step 13H-B).

Diagnostic-only runner for the REAL production chain:

    Config.get_research_config() -> run_live_research() ->
    research_result_to_news_item() -> create_content_plan(persist_history=False)
    -> validate_content_plan() -> human-readable report

It MUST stop before StateService/ContentItem persistence, publication,
copywriting, editing, design, Telegram and any DB/state write. An empty
research shortlist is reported honestly (stop_reason="no_ranked_candidate")
and is NOT hidden behind an editorial fallback. Exceptions propagate
unchanged: this runner fails loudly on implementation defects.

The only intended external side effect is LIVE READ-ONLY network discovery
inside run_live_research(). CLI (diagnostic, no writes):

    python -m src.research.production_dry_run
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from src.agents.strategist import create_content_plan
from src.core.config import Config
from src.research.legacy_bridge import research_result_to_news_item
from src.research.live import run_live_research
from src.utils.validators import validate_content_plan

DRY_RUN_LIMIT = 5


@dataclass(frozen=True)
class ProductionDryRunResult:
    research_result: object
    news_item: dict | None
    plan: dict | None
    validation: dict | None
    used_fallback: bool
    stop_reason: str | None


def run_production_dry_run(
    *,
    now: datetime,
    limit: int = DRY_RUN_LIMIT,
) -> ProductionDryRunResult:
    """Run the live chain once and observe it honestly. No fallback, no catch."""
    research_config = Config.get_research_config()
    research_result = run_live_research(
        now=now,
        limit=limit,
        **research_config.live_kwargs(),
    )
    news_item = research_result_to_news_item(research_result, now=now)

    if news_item is None:
        return ProductionDryRunResult(
            research_result=research_result,
            news_item=None,
            plan=None,
            validation=None,
            used_fallback=False,
            stop_reason="no_ranked_candidate",
        )

    plan = create_content_plan(news_item=news_item, persist_history=False)
    validation = validate_content_plan(plan)

    return ProductionDryRunResult(
        research_result=research_result,
        news_item=news_item,
        plan=plan,
        validation=validation,
        used_fallback=False,
        stop_reason=None,
    )


def format_production_dry_run(result: ProductionDryRunResult) -> str:
    """Concise human-readable report. Display only — nothing is recomputed."""
    research = result.research_result
    lines = [
        "Researcher 2.0 → Strategist LIVE dry run",
        "",
        "Research:",
        f"input={research.input_count}",
        f"deduplicated={research.deduplicated_count}",
        f"classified={research.classified_count}",
        f"verified={research.verified_count}",
        f"scored={research.scored_count}",
        f"ranked={len(research.ranked.ranked)}",
        "",
        "Selected:",
    ]
    if result.news_item is not None:
        item = result.news_item
        lines.append(f"title={item['title']}")
        lines.append(f"source={item['source']}")
        lines.append(f"url={item['url']}")
        lines.append(f"age_hours={item['age_hours']}")
    else:
        lines.append("(empty)")

    lines += ["", "Plan:"]
    if result.plan is not None:
        plan = result.plan
        lines.append(f"topic={plan['topic']}")
        lines.append(f"format={plan['format']}")
        lines.append(f"mode={plan['mode']}")
        lines.append(f"platform={plan['platform']}")
    else:
        lines.append("(empty)")

    lines += ["", "Validation:"]
    if result.validation is not None:
        lines.append(f"valid={result.validation['valid']}")
        lines.append(f"issues={result.validation['issues']}")
    else:
        lines.append("(empty)")

    if result.stop_reason is not None:
        lines.append(f"stop_reason={result.stop_reason}")

    return "\n".join(lines)


def main() -> int:
    now = datetime.now(timezone.utc)
    result = run_production_dry_run(now=now, limit=DRY_RUN_LIMIT)
    print(format_production_dry_run(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
