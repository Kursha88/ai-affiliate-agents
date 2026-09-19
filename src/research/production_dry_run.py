"""Live end-to-end production dry run (Stage 15, Step 15H-A).

Diagnostic-only runner mirroring the CURRENT selected-candidate production
planning chain:

    Config.get_research_config() -> run_live_research() ->
    run_select_stage() -> content_candidate_to_news_item() ->
    run_strategist() -> strategist_plan_to_legacy_plan() ->
    validate_content_plan() -> human-readable report

It MUST stop before persistence, publication, copywriting, editing, design,
social integrations and any DB/state write. An empty SELECT outcome is
reported honestly (stop_reason="no_selected_candidate") and is NOT hidden
behind an editorial fallback. Exceptions propagate unchanged: this runner
fails loudly on implementation defects.

The only intended external side effect is LIVE READ-ONLY network discovery
inside run_live_research(). CLI (diagnostic, no writes):

    python -m src.research.production_dry_run
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from src.core.config import Config
from src.domain.strategist import StrategistPlan
from src.research.legacy_bridge import content_candidate_to_news_item
from src.research.live import run_live_research
from src.research.select_stage import run_select_stage
from src.strategy.legacy_bridge import strategist_plan_to_legacy_plan
from src.strategy.strategist import run_strategist
from src.utils.validators import validate_content_plan

DRY_RUN_LIMIT = 5


@dataclass(frozen=True)
class ProductionDryRunResult:
    research_result: object
    selected_candidate: object | None
    news_item: dict | None
    strategist_plan: StrategistPlan | None
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
    selected_candidate = run_select_stage(research_result)

    if selected_candidate is None:
        return ProductionDryRunResult(
            research_result=research_result,
            selected_candidate=None,
            news_item=None,
            strategist_plan=None,
            plan=None,
            validation=None,
            used_fallback=False,
            stop_reason="no_selected_candidate",
        )

    news_item = content_candidate_to_news_item(selected_candidate, now=now)
    strategist_plan = run_strategist(selected_candidate)
    plan = strategist_plan_to_legacy_plan(
        strategist_plan,
        created_at=now.isoformat(),
        news_source=news_item["source"],
        news_age_hours=news_item["age_hours"],
    )
    validation = validate_content_plan(plan)

    return ProductionDryRunResult(
        research_result=research_result,
        selected_candidate=selected_candidate,
        news_item=news_item,
        strategist_plan=strategist_plan,
        plan=plan,
        validation=validation,
        used_fallback=False,
        stop_reason=None,
    )


def format_production_dry_run(result: ProductionDryRunResult) -> str:
    """Concise human-readable report. Display only — nothing is recomputed."""
    research = result.research_result
    lines = [
        "Researcher 2.0 -> SELECT -> Strategist 2.0 -> Legacy Bridge -> Validation",
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
    selected = result.selected_candidate
    if selected is not None:
        lines.append(f"title={selected.candidate.title}")
        lines.append(f"cluster={selected.candidate.content_cluster.value}")
        selection = selected.selection
        recommended = selection.recommended_format
        fmt = recommended.value if recommended is not None else ""
        lines.append(f"format={fmt}")
        lines.append(f"research_required={selection.research_required}")
        lines.append(f"experiment_required={selection.experiment_required}")
    else:
        lines.append("(empty)")

    lines += ["", "Legacy news_item:"]
    if result.news_item is not None:
        item = result.news_item
        lines.append(f"title={item['title']}")
        lines.append(f"source={item['source']}")
        lines.append(f"url={item['url']}")
        lines.append(f"age_hours={item['age_hours']}")
    else:
        lines.append("(empty)")

    lines += ["", "Strategist 2.0:"]
    strategist_plan = result.strategist_plan
    if strategist_plan is not None:
        lines.append(f"candidate_id={strategist_plan.candidate_id}")
        lines.append(f"topic={strategist_plan.topic}")
        lines.append(f"cluster={strategist_plan.content_cluster.value}")
        lines.append(f"format={strategist_plan.content_format.value}")
        lines.append(
            "platforms=" + ",".join(p.value for p in strategist_plan.target_platforms)
        )
        lines.append(f"research_required={strategist_plan.research_required}")
        lines.append(f"experiment_required={strategist_plan.experiment_required}")
        lines.append(f"angle={strategist_plan.angle}")
        lines.append(f"hook={strategist_plan.hook}")
        lines.append(f"objective={strategist_plan.objective}")
        lines.append(f"cta={strategist_plan.cta}")
        lines.append(f"cta_link={strategist_plan.cta_link}")
        lines.append(f"tone={strategist_plan.tone}")
        lines.append("structure=" + ",".join(strategist_plan.structure))
        lines.append(f"language={strategist_plan.language}")
        lines.append(f"mode={strategist_plan.mode}")
    else:
        lines.append("(empty)")

    lines += ["", "Plan:"]
    if result.plan is not None:
        plan = result.plan
        lines.append(f"topic={plan['topic']}")
        lines.append(f"format={plan['format']}")
        lines.append(f"content_format={plan['content_format']}")
        lines.append(f"content_cluster={plan['content_cluster']}")
        lines.append("target_platforms=" + ",".join(plan["target_platforms"]))
        lines.append(f"research_required={plan['research_required']}")
        lines.append(f"experiment_required={plan['experiment_required']}")
        lines.append(f"angle={plan['angle']}")
        lines.append(f"hook={plan['hook']}")
        lines.append(f"objective={plan['objective']}")
        lines.append(f"tone={plan['tone']}")
        lines.append("structure=" + ",".join(plan["structure"]))
        lines.append(f"language={plan['language']}")
        lines.append(f"mode={plan['mode']}")
        lines.append(f"platform={plan['platform']}")
        lines.append(f"cta={plan['cta']}")
        lines.append(f"cta_link={plan['cta_link']}")
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
