"""Deterministic Strategist Policy Engine (Stage 15, Step 15D-B).

Pure, deterministic editorial policy:

    StrategistInput → deterministic editorial policy → StrategistEnrichment

The engine owns ONLY strategist-owned enrichment:

    angle, hook, objective, cta, cta_link, tone, structure, language, mode

It never modifies, replaces, recomputes or returns the SELECT-owned
decision fields; these stay in the bound ``ContentCandidate`` and are
forwarded unchanged by the later plan-building step.

Core policy principle:

    ContentFormat defines the PRIMARY editorial policy (objective, tone,
    structure, cta). ContentCluster only refines ANGLE. The cluster can
    never change objective/structure/tone/cta/cta_link/language/mode.

Determinism guarantees:

    - Immutable module-level mapping tables keyed by real enum members.
    - ``hook`` is exactly the original title; ``cta_link`` is exactly the
      original ``source_url`` — no rewriting, stripping or normalization.
    - ``language="ru"`` and ``mode="growth"`` are fixed policy constants.
    - No AI, no network, no clock, no filesystem, no env access, no
      persistence, no exception handling, no fallback mappings.

Strict field access — the function reads ONLY:

    content_candidate.selection
    selection.recommended_format
    content_candidate.candidate.content_cluster
    content_candidate.candidate.title
    content_candidate.candidate.source_url

and nothing else about the selection or the discovery record is ever
touched — the SELECT-owned decision fields and every other discovery
attribute are deliberately ignored by this policy.
"""

from src.domain.strategy import ContentCluster, ContentFormat
from src.domain.strategist import StrategistEnrichment, StrategistInput

__all__ = ["build_strategist_enrichment"]

_ERROR_MISSING_SELECTION = "strategist input missing strategic selection"
_ERROR_MISSING_FORMAT = "strategist input missing recommended format"
_ERROR_MISSING_CLUSTER = "strategist input missing content cluster"
_ERROR_UNSUPPORTED_FORMAT = "unsupported content format"
_ERROR_UNSUPPORTED_CLUSTER = "unsupported content cluster"

# Strategist 2.0 deterministic policy constants (this step).
_LANGUAGE = "ru"
_MODE = "growth"

# ──────────────────────────────────────────────────────────────────────
# FORMAT POLICY — ContentFormat is the authoritative editorial policy.
# Immutable table keyed by real ContentFormat members; ``structure``
# values are tuples. No fallback exists.
# ──────────────────────────────────────────────────────────────────────

_FORMAT_POLICIES = {
    ContentFormat.BREAKING_NEWS: (
        "Быстро объяснить, что произошло и почему это важно",
        "оперативный и фактический",
        (
            "hook",
            "what_happened",
            "why_it_matters",
            "takeaway",
            "cta",
        ),
        "Проверить первоисточник",
    ),
    ContentFormat.TOOL_DISCOVERY: (
        "Показать, зачем нужен инструмент и где он полезен",
        "практичный и конкретный",
        (
            "problem",
            "tool",
            "key_features",
            "use_case",
            "cta",
        ),
        "Изучить инструмент",
    ),
    ContentFormat.PRACTICAL_GUIDE: (
        "Научить выполнить конкретную задачу шаг за шагом",
        "обучающий и практичный",
        (
            "hook",
            "prerequisites",
            "steps",
            "result",
            "cta",
        ),
        "Повторить шаги",
    ),
    ContentFormat.COMPARISON: (
        "Помочь сравнить варианты и понять их различия",
        "аналитический и нейтральный",
        (
            "context",
            "option_a",
            "option_b",
            "tradeoffs",
            "recommendation",
            "cta",
        ),
        "Сравнить варианты",
    ),
    ContentFormat.EXPERIMENT: (
        "Проверить гипотезу на практическом эксперименте",
        "исследовательский и прозрачный",
        (
            "hypothesis",
            "setup",
            "test",
            "result",
            "takeaway",
            "cta",
        ),
        "Повторить эксперимент",
    ),
    ContentFormat.WORKFLOW: (
        "Показать повторяемый рабочий процесс от задачи до результата",
        "системный и практичный",
        (
            "problem",
            "workflow",
            "steps",
            "result",
            "cta",
        ),
        "Попробовать этот процесс",
    ),
    ContentFormat.PROMPT: (
        "Дать готовый способ решить задачу с помощью промта",
        "прикладной и понятный",
        (
            "problem",
            "prompt",
            "how_to_use",
            "expected_result",
            "cta",
        ),
        "Попробовать промт",
    ),
    ContentFormat.CASE_STUDY: (
        "Разобрать реальный кейс, результат и практические выводы",
        "аналитический и прикладной",
        (
            "context",
            "approach",
            "result",
            "lessons",
            "cta",
        ),
        "Применить выводы",
    ),
    ContentFormat.OPINION_ANALYSIS: (
        "Разобрать позицию через аргументы, факты и контраргументы",
        "аналитический и взвешенный",
        (
            "thesis",
            "evidence",
            "counterpoint",
            "conclusion",
            "cta",
        ),
        "Изучить аргументы",
    ),
    ContentFormat.ROUNDUP: (
        "Собрать несколько полезных вариантов и показать различия между ними",
        "обзорный и практичный",
        (
            "intro",
            "items",
            "differences",
            "recommendation",
            "cta",
        ),
        "Изучить подборку",
    ),
}

# ──────────────────────────────────────────────────────────────────────
# CLUSTER → ANGLE POLICY — ContentCluster only refines the angle.
# Immutable table keyed by real ContentCluster members. No fallback.
# ──────────────────────────────────────────────────────────────────────

_CLUSTER_ANGLES = {
    ContentCluster.VIBE_CODING: "Как это меняет практический процесс разработки",
    ContentCluster.AI_AGENTS: "Как использовать AI-агентов для выполнения реальных задач",
    ContentCluster.AI_TOOLS: "Как инструмент решает конкретную практическую проблему",
    ContentCluster.AUTOMATION: "Как автоматизировать повторяемую работу и сократить ручные действия",
    ContentCluster.FREE_AI: "Что можно получить бесплатно и какие есть ограничения",
    ContentCluster.PRACTICAL_EXPERIMENTS: "Что происходит при практической проверке идеи",
    ContentCluster.AI_NEWS: "Что изменилось и какое практическое значение это имеет",
}


def build_strategist_enrichment(
    strategist_input: StrategistInput,
) -> StrategistEnrichment:
    """Build the strategist-owned enrichment for a selected candidate.

    Deterministic: the same ``StrategistInput`` always yields an equal
    ``StrategistEnrichment``. Raises ``ValueError`` with an exact message
    on malformed input, in the documented validation order:

        1. missing strategic selection
        2. missing recommended format
        3. missing content cluster

    and on any unsupported format/cluster value reaching the policy
    tables. Performs no mutation, no AI, no I/O of any kind.
    """
    candidate = strategist_input.content_candidate

    # 1. A strategic selection must exist (bound unchanged from SELECT).
    if candidate.selection is None:
        raise ValueError(_ERROR_MISSING_SELECTION)

    selection = candidate.selection

    # 2. SELECT must have recommended a concrete format.
    if selection.recommended_format is None:
        raise ValueError(_ERROR_MISSING_FORMAT)

    # 3. Classification must have produced an explicit content cluster.
    if candidate.candidate.content_cluster is None:
        raise ValueError(_ERROR_MISSING_CLUSTER)

    content_format = selection.recommended_format
    content_cluster = candidate.candidate.content_cluster
    title = candidate.candidate.title

    # Format policy lookup — explicit membership, no fallback dict lookup.
    if content_format not in _FORMAT_POLICIES:
        raise ValueError(_ERROR_UNSUPPORTED_FORMAT)
    objective, tone, structure, cta = _FORMAT_POLICIES[content_format]

    # Cluster → angle lookup — explicit membership, no fallback dict lookup.
    if content_cluster not in _CLUSTER_ANGLES:
        raise ValueError(_ERROR_UNSUPPORTED_CLUSTER)
    angle = _CLUSTER_ANGLES[content_cluster]

    # Hook policy: exactly the original title — this step is NOT copywriting.
    # CTA-link policy: exactly the original source_url — never rewritten.
    return StrategistEnrichment(
        angle=angle,
        hook=title,
        objective=objective,
        cta=cta,
        cta_link=candidate.candidate.source_url,
        tone=tone,
        structure=structure,
        language=_LANGUAGE,
        mode=_MODE,
    )
