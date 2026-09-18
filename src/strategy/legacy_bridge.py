"""Lossless StrategistPlan → legacy-plan compatibility bridge (Stage 15, Step 15F).

PURE compatibility adapter: ``StrategistPlan`` → legacy-compatible dict.
It exists only so existing downstream code can consume Strategist 2.0
output during migration. The bridge makes NO editorial decisions, never
reinterprets ``ContentFormat`` and never calls the old Strategist.

Information preservation rules:

    - Every StrategistPlan field survives into the returned dict.
    - Enum members are converted ONLY to their ``.value`` strings where
      explicitly mapped below (format/content_format/content_cluster/
      target_platforms) — never to old Russian format labels.
    - ``structure`` is forwarded BY IDENTITY (the exact same tuple
      object), with no list conversion.
    - ``target_platforms`` keeps its order exactly — no sorting, no
      reordering, nothing added or removed.
    - The adapter performs NO semantic validation: empty strings, an
      empty ``target_platforms`` tuple, an unusual mode/language or an
      empty ``cta_link`` are all preserved as-is. Existing validators
      remain separate and are not called here.

All three compatibility metadata arguments (``created_at``,
``news_source``, ``news_age_hours``) are required keyword-only inputs
supplied by the caller — the bridge reads no clock, no config, no env
access, no filesystem, and persists nothing.
"""

from src.domain.strategist import StrategistPlan

__all__ = ["strategist_plan_to_legacy_plan"]

_LEGACY_PLATFORM = "telegram"

_NEUTRAL_PRODUCT_ID = "source"
_NEUTRAL_PRODUCT_CATEGORY = "Source"
_NEUTRAL_PRODUCT_STATUS = "active"
_NEUTRAL_FREE_TRIAL = False
_NEUTRAL_IS_AFFILIATE = False


def strategist_plan_to_legacy_plan(
    plan: StrategistPlan,
    *,
    created_at: str,
    news_source: str,
    news_age_hours: float,
) -> dict:
    """Adapt a StrategistPlan into a legacy-compatible content-plan dict.

    Lossless: all SELECT-owned decisions and all strategist-owned
    enrichment fields are forwarded exactly; enums serialize only to
    their ``.value`` strings; ``structure`` keeps its tuple identity.
    The compatibility metadata (``created_at``, ``news_source``,
    ``news_age_hours``) is taken verbatim from the required arguments —
    never derived, normalized or validated.
    """
    product = {
        "id": _NEUTRAL_PRODUCT_ID,
        "name": plan.topic,
        "description": plan.angle,
        "category": _NEUTRAL_PRODUCT_CATEGORY,
        "affiliate_link": plan.cta_link,
        "free_trial": _NEUTRAL_FREE_TRIAL,
        "status": _NEUTRAL_PRODUCT_STATUS,
    }

    news = {
        "source": news_source,
        "url": plan.cta_link,
        "age_hours": news_age_hours,
    }

    return {
        "created_at": created_at,
        "mode": plan.mode,
        "platform": _LEGACY_PLATFORM,
        "candidate_id": plan.candidate_id,
        "topic": plan.topic,
        "format": plan.content_format.value,
        "content_format": plan.content_format.value,
        "content_cluster": plan.content_cluster.value,
        "target_platforms": tuple(
            platform.value for platform in plan.target_platforms
        ),
        "research_required": plan.research_required,
        "experiment_required": plan.experiment_required,
        "angle": plan.angle,
        "hook": plan.hook,
        "objective": plan.objective,
        "tone": plan.tone,
        "structure": plan.structure,
        "news": news,
        "product": product,
        "language": plan.language,
        "cta": plan.cta,
        "cta_link": plan.cta_link,
        "is_affiliate": _NEUTRAL_IS_AFFILIATE,
    }
