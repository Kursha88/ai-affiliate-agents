"""Deterministic SELECT stage for ranked candidates (Stage 3.2, Step 14A).

Converts ONE existing ``RankedCandidate`` from the RANK stage into the
already-existing ``StrategicSelection`` domain contract:

    DISCOVER -> NORMALIZE -> DEDUPLICATE -> CLASSIFY -> VERIFY -> SCORE
    -> RANK -> SELECT

Semantics: the selector decides editorial suitability for ONE candidate.
It does NOT choose between multiple ranked candidates, does NOT inspect
rank position or ``candidate_id``, does NOT perform TOP-1 selection, and
does NOT re-score or re-rank. Multi-candidate selection is a later step.

Decision rules (deterministic, in order):

1. ``candidate.cluster is None``          -> not selected
   (``selection_reason="missing_cluster"``).
2. ``candidate.final_rank_score < SELECTION_MIN_SCORE`` -> not selected
   (``selection_reason="below_selection_threshold"``). A score exactly
   equal to ``SELECTION_MIN_SCORE`` IS selected.
3. Selected candidates map through a fixed cluster table:
   cluster -> (recommended_format, target_platforms, research_required,
   experiment_required, selection_reason).
4. A non-None cluster that is not one of the seven ``ContentCluster``
   values raises ``ValueError("unsupported content cluster")`` — no
   silent defaults.

The selector reads ONLY ``candidate.cluster`` and
``candidate.final_rank_score`` — never title, URL, source, verification,
score components, metadata or discovery content.

Boundaries: pure function — no network/filesystem/DB/environment/clock/
random, no AI/API calls, no mutation of the candidate or the enums, no
modification of ``StrategicSelection``, no recomputation of rank scores.
"""

from __future__ import annotations

from src.domain.strategy import (
    ContentCluster,
    ContentFormat,
    StrategicSelection,
    TargetPlatform,
)
from src.research.rank import RankedCandidate

#: Minimum ``RankedCandidate.final_rank_score`` for selection.
#: A score exactly equal to this value IS selected.
SELECTION_MIN_SCORE: float = 5.0

# ──────────────────────────────────────────────────────────────────────
# Fixed cluster -> selection mapping (editorial DATA, deterministic).
# (recommended_format, target_platforms, research_required,
#  experiment_required, selection_reason)
# ──────────────────────────────────────────────────────────────────────

_CLUSTER_SELECTIONS: dict = {
    ContentCluster.VIBE_CODING: (
        ContentFormat.PRACTICAL_GUIDE,
        (
            TargetPlatform.TELEGRAM,
            TargetPlatform.X,
            TargetPlatform.LINKEDIN,
            TargetPlatform.YOUTUBE_SHORTS,
            TargetPlatform.TIKTOK,
        ),
        False,
        False,
        "selected_vibe_coding",
    ),
    ContentCluster.AI_AGENTS: (
        ContentFormat.WORKFLOW,
        (
            TargetPlatform.TELEGRAM,
            TargetPlatform.X,
            TargetPlatform.LINKEDIN,
        ),
        False,
        False,
        "selected_ai_agents",
    ),
    ContentCluster.AI_TOOLS: (
        ContentFormat.TOOL_DISCOVERY,
        (
            TargetPlatform.TELEGRAM,
            TargetPlatform.X,
            TargetPlatform.LINKEDIN,
            TargetPlatform.PINTEREST,
        ),
        False,
        False,
        "selected_ai_tools",
    ),
    ContentCluster.AUTOMATION: (
        ContentFormat.WORKFLOW,
        (
            TargetPlatform.TELEGRAM,
            TargetPlatform.X,
            TargetPlatform.LINKEDIN,
        ),
        False,
        False,
        "selected_automation",
    ),
    ContentCluster.FREE_AI: (
        ContentFormat.COMPARISON,
        (
            TargetPlatform.TELEGRAM,
            TargetPlatform.X,
            TargetPlatform.LINKEDIN,
            TargetPlatform.PINTEREST,
        ),
        False,
        False,
        "selected_free_ai",
    ),
    ContentCluster.PRACTICAL_EXPERIMENTS: (
        ContentFormat.EXPERIMENT,
        (
            TargetPlatform.TELEGRAM,
            TargetPlatform.X,
            TargetPlatform.LINKEDIN,
            TargetPlatform.YOUTUBE_SHORTS,
            TargetPlatform.TIKTOK,
        ),
        False,
        True,
        "selected_practical_experiments",
    ),
    ContentCluster.AI_NEWS: (
        ContentFormat.BREAKING_NEWS,
        (
            TargetPlatform.TELEGRAM,
            TargetPlatform.X,
            TargetPlatform.LINKEDIN,
        ),
        True,
        False,
        "selected_ai_news",
    ),
}


def _not_selected(selection_reason: str) -> StrategicSelection:
    """Uniform rejection shape for a ranked candidate."""
    return StrategicSelection(
        selected=False,
        selection_reason=selection_reason,
        recommended_format=None,
        target_platforms=(),
        research_required=False,
        experiment_required=False,
    )


def select_ranked_candidate(candidate: RankedCandidate) -> StrategicSelection:
    """Map ONE ranked candidate to its ``StrategicSelection``.

    Reads only ``candidate.cluster`` and ``candidate.final_rank_score``.
    Deterministic: the same input always produces an equal selection.
    """
    if candidate.cluster is None:
        return _not_selected("missing_cluster")

    if candidate.final_rank_score < SELECTION_MIN_SCORE:
        return _not_selected("below_selection_threshold")

    # ContentCluster is a StrEnum, so value-equal strings resolve too;
    # anything else is an unknown cluster and must fail loudly.
    spec = _CLUSTER_SELECTIONS.get(candidate.cluster)
    if spec is None:
        raise ValueError("unsupported content cluster")

    recommended_format, target_platforms, research_required, experiment_required, reason = spec
    return StrategicSelection(
        selected=True,
        selection_reason=reason,
        recommended_format=recommended_format,
        target_platforms=target_platforms,
        research_required=research_required,
        experiment_required=experiment_required,
    )
