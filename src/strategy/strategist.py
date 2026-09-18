"""Strategist 2.0 composition core (Stage 15, Step 15E).

Pure, deterministic composition of the existing Strategist layers:

    ContentCandidate
        → validated StrategistInput   (Step 15B boundary)
        → StrategistEnrichment        (Step 15D-B policy engine)
        → StrategistPlan              (Step 15C assembler)

This module adds NO editorial policy, NO validation, NO legacy
conversion and NO production wiring. It only calls, in order:

    1. ``build_strategist_input(content_candidate)``
       — the validated boundary layer owns every SELECT-stage
       invariant (stage, selection, selected, format, platforms,
       cluster) and raises ``ValueError`` with an exact message on
       the first failure; that error propagates unchanged.
    2. ``build_strategist_enrichment(strategist_input)``
       — the policy engine owns all strategist-owned enrichment.
    3. ``build_strategist_plan(...)``
       — the assembler forwards the SELECT-owned decision fields
       losslessly from the candidate and attaches the enrichment
       fields via explicit keyword arguments.

The exact ``StrategistInput`` object produced by step 1 is passed to
both step 2 and step 3, and every enrichment field flows unchanged
from the ``StrategistEnrichment`` object into the plan — lossless,
identity-preserving composition. No object is mutated.
"""

from src.domain.strategy import ContentCandidate
from src.domain.strategist import StrategistPlan
from src.strategy.strategist_input import build_strategist_input
from src.strategy.strategist_policy import build_strategist_enrichment
from src.strategy.strategist_plan import build_strategist_plan

__all__ = ["run_strategist"]


def run_strategist(
    content_candidate: ContentCandidate,
) -> StrategistPlan:
    """Run the full deterministic Strategist 2.0 core for one candidate.

    Composition only: boundary validation, policy enrichment and plan
    assembly each remain owned by their existing layers. ``ValueError``
    from any layer propagates unchanged. Deterministic: the same
    candidate always yields an equal ``StrategistPlan``.
    """
    strategist_input = build_strategist_input(content_candidate)

    enrichment = build_strategist_enrichment(strategist_input)

    return build_strategist_plan(
        strategist_input,
        angle=enrichment.angle,
        hook=enrichment.hook,
        objective=enrichment.objective,
        cta=enrichment.cta,
        cta_link=enrichment.cta_link,
        tone=enrichment.tone,
        structure=enrichment.structure,
        language=enrichment.language,
        mode=enrichment.mode,
    )
