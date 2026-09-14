"""Project a selected ProcessedCandidate into ContentCandidate (Step 14D).

SELECT-stage projection:

    ProcessedCandidate + StrategicSelection -> ContentCandidate

Uses the EXISTING domain models (``DiscoveryCandidate``,
``ContentCandidate``, ``CandidateStage``) — no new domain contracts.

Preconditions (no other semantic validation):

1. ``selection.selected`` must be True, otherwise
   ``ValueError("strategic selection is not selected")``.
2. ``processed.classification.cluster`` must not be None, otherwise
   ``ValueError("selected processed candidate missing content cluster")``.
3. ``processed.score`` must not be None, otherwise
   ``ValueError("selected processed candidate missing score")``.

Mapping rules:

- ``DiscoveryCandidate`` is NEWLY constructed (``RawDiscovery`` and
  ``DiscoveryCandidate`` are different domain types).
- ``metadata`` is a NEW dict equal to ``raw.metadata`` — never the same
  object; ``raw.metadata`` is never mutated.
- ``raw.url is None`` -> ``source_url=""``; otherwise the exact string
  is preserved (never ``str(...)``-coerced).
- ``verification`` / ``score`` / ``selection`` are preserved BY IDENTITY.
- ``stage`` is always ``CandidateStage.SELECTED`` — research/experiment
  transitions are later workflow steps.
- ``content_id`` stays ``None`` (no persistence, no id creation).

RawDiscovery-only fields (``identifiers``, ``comments_count``,
``raw_score_label``) intentionally have no ``DiscoveryCandidate`` field
and are NOT invented into metadata here — that concern is a later step.

The projection source of truth is ``ProcessedCandidate`` +
``StrategicSelection``. ``RankedCandidate`` was resolved earlier (Step
14C) and must not appear here.
"""

from __future__ import annotations

from src.domain.strategy import (
    CandidateStage,
    ContentCandidate,
    DiscoveryCandidate,
    StrategicSelection,
)
from src.research.researcher import ProcessedCandidate


def build_selected_content_candidate(
    processed: ProcessedCandidate,
    selection: StrategicSelection,
) -> ContentCandidate:
    """Build the domain ContentCandidate for one selected candidate."""
    if not selection.selected:
        raise ValueError("strategic selection is not selected")
    if processed.classification.cluster is None:
        raise ValueError("selected processed candidate missing content cluster")
    if processed.score is None:
        raise ValueError("selected processed candidate missing score")

    raw = processed.discovery
    discovery_candidate = DiscoveryCandidate(
        candidate_id=processed.candidate_id,
        title=raw.title,
        source_type=processed.source_type,
        source_url=raw.url if raw.url is not None else "",
        discovered_at=raw.discovered_at,
        content_cluster=processed.classification.cluster,
        source_name=raw.source_name,
        published_at=raw.published_at,
        summary=raw.summary,
        raw_score=raw.raw_score,
        metadata=dict(raw.metadata),
    )
    return ContentCandidate(
        candidate=discovery_candidate,
        verification=processed.verification,
        score=processed.score,
        selection=selection,
        stage=CandidateStage.SELECTED,
        content_id=None,
    )
