"""Deterministic candidate scoring (Stage 3.2).

Consumes the already-computed upstream stage outputs and produces a
``CandidateScore`` — the SCORE stage of the intelligence pipeline:

    DISCOVER -> NORMALIZE -> DEDUPLICATE -> CLASSIFY -> VERIFY -> SCORE -> RANK

Composability contract (Stage 3.2 decisions, final):

- ``score_candidate`` NEVER re-runs classification or verification.
  ``classification`` and ``verification`` are accepted as the result
  objects produced by ``classify()`` / ``verify_provenance()`` and are
  only read. Neither ``classify`` nor ``verify_provenance`` is callable
  from this module (structurally tested).
- ``classification`` is accepted but UNUSED in Phase 1 (no damping,
  no cluster-aware scoring) — reserved for future refinement.
  ``CLUSTER_PRIORITY`` must never appear here: editorial weighting
  belongs to ranking/selection, not to scoring.
- ``verification`` is validated with the existing
  ``validate_verification()`` before use. An invalid
  ``VerificationResult`` raises ``ValueError``. DISPUTED / REJECTED
  provenance also raises ``ValueError``: such records must be filtered
  out by the orchestrator before scoring, not silently scored 0.

Component models (all deterministic, all test-visible constants):

- ``novelty``: age bands against the INJECTED ``now`` (no hidden clock
  anywhere in this module). Unknown/invalid ``published_at`` scores the
  conservative floor (no freshness evidence is never average evidence).
  Future timestamps are clamped to age 0.
- ``practical_utility``: small weighted whole-word phrase rules over
  title+summary, summed and capped to 0..10.
- ``free_availability``: weighted rules with strong/medium/weak tiers
  and explicit negative rules ("free speech", "free trial") so common
  false positives cannot inflate the component. The GITHUB source bonus
  is applied ONLY where positive free/open evidence already exists —
  GitHub alone must never imply free.
- ``audience_interest``: log-scaled engagement (max of non-negative
  ``raw_score`` and ``comments_count``), capped at 10, floored at 3
  when no engagement evidence exists.
- ``viral_potential``: log-scaled engagement velocity
  (``engagement / max(age_hours, 0.5)``), capped at 10, floored at 3
  when engagement OR age is missing.
- ``credibility``: deterministic mapping of provenance strength
  (``VerificationResult.confidence`` is provenance strength, not
  probability) — VERIFIED: ``5 + 5*conf``; UNVERIFIED: ``10*conf``;
  DISPUTED/REJECTED: ``ValueError``.

Boundaries: no DB/network/filesystem/random, no ``datetime.now()``/
``utcnow()`` (``now`` is injected), no ranking, no selection, no
``MIN_CONFIDENCE_FOR_SELECTION``, no persistence, no mutation of
``RawDiscovery``, no ``DiscoveryCandidate`` construction, and
``total_score`` is never stored — it remains the computed property of
``CandidateScore`` derived from ``DEFAULT_SCORING_WEIGHTS``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.domain.strategy import (
    DEFAULT_SCORING_WEIGHTS,
    CandidateScore,
    SourceType,
    VerificationResult,
    VerificationStatus,
    validate_verification,
)
from src.research.adapters.base import RawDiscovery
from src.research.classify import ClassificationResult
from src.research.normalize import normalize_title

# ──────────────────────────────────────────────────────────────────────
# Novelty (age bands, hours) — upper bounds, evaluated in order.
# ──────────────────────────────────────────────────────────────────────

#: (age_hours_upper_bound, score) — first band whose bound covers the age.
NOVELTY_AGE_BANDS: Tuple[Tuple[float, float], ...] = (
    (6.0, 10.0),
    (24.0, 8.0),
    (48.0, 6.0),
    (72.0, 4.0),
)
NOVELTY_OLDER_SCORE: float = 2.0
#: Missing/invalid published_at — conservative: no freshness evidence
#: never scores as fresh evidence.
NOVELTY_MISSING_SCORE: float = 2.0

# ──────────────────────────────────────────────────────────────────────
# Practical utility rules (weighted whole-word phrases, title+summary).
# ──────────────────────────────────────────────────────────────────────

UTILITY_RULES: Tuple[Tuple[str, float], ...] = (
    ("how to", 3.0),
    ("step by step", 3.0),
    ("step-by-step", 3.0),
    ("tutorial", 2.5),
    ("guide", 2.0),
    ("template", 2.0),
    ("workflow", 2.0),
    ("integration", 2.0),
    ("example", 1.5),
    ("setup", 1.5),
    ("implementation", 1.5),
)

# ──────────────────────────────────────────────────────────────────────
# Free-availability rules (strong/medium/weak + negatives).
# ──────────────────────────────────────────────────────────────────────

FREE_STRONG_RULES: Tuple[Tuple[str, float], ...] = (
    ("open source", 3.0),
    ("open-source", 3.0),
    ("open weights", 3.0),
    ("open-weights", 3.0),
    ("self-hosted", 3.0),
    ("self hosted", 3.0),
)
FREE_MEDIUM_RULES: Tuple[Tuple[str, float], ...] = (
    ("free tier", 2.5),
    ("free plan", 2.5),
    ("no api key", 2.5),
)
#: Deliberately weak so bare "free" can dominate nothing; negatives below
#: keep the most common false positives from firing at all.
FREE_WEAK_RULES: Tuple[Tuple[str, float], ...] = (
    ("free", 1.0),
)
#: Negative/conflict rules subtract weight (mirrors classify's concept).
FREE_NEGATIVE_RULES: Tuple[Tuple[str, float], ...] = (
    ("free speech", -3.0),
    ("free trial", -2.0),
)

#: Weak GITHUB source affinity — applied ONLY to free_availability and
#: ONLY where positive free/open evidence already exists. GitHub alone
#: must never imply free (0.5 can never create evidence from nothing).
FREE_SOURCE_GITHUB_BONUS: float = 0.5

# ──────────────────────────────────────────────────────────────────────
# Audience / viral log scaling.
# ──────────────────────────────────────────────────────────────────────

#: Engagement value that maps to a full 10.0 audience score.
AUDIENCE_CAP_ENGAGEMENT: float = 300.0
#: Engagement velocity (engagement/hour) that maps to a full 10.0 viral score.
VIRAL_CAP_VELOCITY: float = 50.0
#: Floors when the required evidence is missing entirely.
AUDIENCE_MISSING_FLOOR: float = 3.0
VIRAL_MISSING_FLOOR: float = 3.0
#: Velocity time floor (hours) — a 1-minute-old post cannot divide by ~0.
VIRAL_MIN_AGE_HOURS: float = 0.5

SCORE_MIN: float = 0.0
SCORE_MAX: float = 10.0


@dataclass(frozen=True)
class ScoreRuleMatch:
    """One matched rule instance (observable per-component evidence)."""

    component: str
    rule: str
    weight: float


@dataclass(frozen=True)
class ScoreResult:
    """Score plus concise per-component evidence for debugging/tests.

    ``score`` is the sole pipeline artifact; the evidence fields are
    observability only and never feed back into scoring.
    """

    score: CandidateScore
    matched_rules: Tuple[ScoreRuleMatch, ...]
    novelty_age_hours: Optional[float]
    engagement: Optional[float]
    velocity: Optional[float]
    reason: str = "scored"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score.to_dict(),
            "matched_rules": [
                {"component": m.component, "rule": m.rule, "weight": m.weight}
                for m in self.matched_rules
            ],
            "novelty_age_hours": self.novelty_age_hours,
            "engagement": self.engagement,
            "velocity": self.velocity,
            "reason": self.reason,
        }


# ──────────────────────────────────────────────────────────────────────
# Rule matching helpers (same conservative shape as classify.py)
# ──────────────────────────────────────────────────────────────────────


def _matches_phrase(text: str, phrase: str) -> bool:
    """Whole-word phrase containment on normalized text.

    Patterns are normalized with ``normalize_title`` exactly like the
    text, so matching is case-insensitive and whitespace-stable. ASCII
    word-boundary lookarounds (same convention as classify.py) plus a
    trailing plural tolerance prevent substring false positives
    (``guide`` must not fire inside ``misguided``).
    """
    pattern = normalize_title(phrase)
    if not pattern:
        return False
    escaped = re.escape(pattern)
    if escaped[-1].isalpha() and len(pattern) > 2:
        escaped += "s?"
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def _sum_rules(
    text: str,
    rules: Tuple[Tuple[str, float], ...],
    component: str,
    matched: List[ScoreRuleMatch],
) -> float:
    """Sum weights of matched rules; record each match once."""
    total = 0.0
    for phrase, weight in rules:
        if _matches_phrase(text, phrase):
            matched.append(ScoreRuleMatch(component, phrase, weight))
            total += weight
    return total


def _clamp_score(value: float) -> float:
    return round(min(SCORE_MAX, max(SCORE_MIN, value)), 4)


def _novelty(discovery: RawDiscovery, *, now: datetime) -> Tuple[float, Optional[float]]:
    """Age-band novelty; returns (score, age_hours_or_None)."""
    published_raw = discovery.published_at
    if not isinstance(published_raw, str) or not published_raw.strip():
        return NOVELTY_MISSING_SCORE, None
    try:
        published = datetime.fromisoformat(published_raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return NOVELTY_MISSING_SCORE, None

    age = (now - published).total_seconds() / 3600.0
    if age < 0.0:
        age = 0.0  # future timestamp (clock skew) clamps to age 0

    for bound, score in NOVELTY_AGE_BANDS:
        if age <= bound:
            return score, age
    return NOVELTY_OLDER_SCORE, age


def _practical_utility(
    discovery: RawDiscovery, matched: List[ScoreRuleMatch]
) -> float:
    text = normalize_title(f"{discovery.title} {discovery.summary}")
    return _clamp_score(_sum_rules(text, UTILITY_RULES, "practical_utility", matched))


def _free_availability(
    discovery: RawDiscovery,
    source_type: Optional[SourceType],
    matched: List[ScoreRuleMatch],
) -> float:
    text = normalize_title(f"{discovery.title} {discovery.summary}")
    positives = _sum_rules(text, FREE_STRONG_RULES, "free_availability", matched)
    positives += _sum_rules(text, FREE_MEDIUM_RULES, "free_availability", matched)
    positives += _sum_rules(text, FREE_WEAK_RULES, "free_availability", matched)
    negatives = _sum_rules(text, FREE_NEGATIVE_RULES, "free_availability", matched)

    # Weak source affinity ONLY on top of existing positive evidence.
    if (
        source_type == SourceType.GITHUB
        and positives > 0.0
    ):
        positives += FREE_SOURCE_GITHUB_BONUS
        matched.append(
            ScoreRuleMatch("free_availability", "source_affinity:github", FREE_SOURCE_GITHUB_BONUS)
        )

    return _clamp_score(positives + negatives)


def _engagement(discovery: RawDiscovery) -> Optional[float]:
    """max(non-negative raw_score, comments_count); None when absent."""
    values: List[float] = []
    if (
        isinstance(discovery.raw_score, (int, float))
        and not isinstance(discovery.raw_score, bool)
        and discovery.raw_score >= 0
    ):
        values.append(float(discovery.raw_score))
    if (
        isinstance(discovery.comments_count, int)
        and not isinstance(discovery.comments_count, bool)
        and discovery.comments_count >= 0
    ):
        values.append(float(discovery.comments_count))
    return max(values) if values else None


def _audience_interest(
    engagement: Optional[float], matched: List[ScoreRuleMatch]
) -> float:
    if engagement is None:
        matched.append(
            ScoreRuleMatch("audience_interest", "missing_engagement_floor", AUDIENCE_MISSING_FLOOR)
        )
        return AUDIENCE_MISSING_FLOOR
    scaled = 10.0 * math.log1p(engagement) / math.log1p(AUDIENCE_CAP_ENGAGEMENT)
    return _clamp_score(scaled)


def _viral_potential(
    engagement: Optional[float],
    age_hours: Optional[float],
    matched: List[ScoreRuleMatch],
) -> float:
    if engagement is None or age_hours is None:
        matched.append(
            ScoreRuleMatch("viral_potential", "missing_evidence_floor", VIRAL_MISSING_FLOOR)
        )
        return VIRAL_MISSING_FLOOR
    velocity = engagement / max(age_hours, VIRAL_MIN_AGE_HOURS)
    scaled = 10.0 * math.log1p(velocity) / math.log1p(VIRAL_CAP_VELOCITY)
    return _clamp_score(scaled)


def _credibility(verification: VerificationResult) -> float:
    """Deterministic provenance-strength -> credibility mapping.

    Caller must have validated ``verification`` (see ``score_candidate``):
    VERIFIED = 5 + 5*conf, UNVERIFIED = 10*conf. DISPUTED/REJECTED never
    reach this function.
    """
    confidence = float(verification.confidence)
    if verification.verification_status == VerificationStatus.VERIFIED:
        return _clamp_score(5.0 + 5.0 * confidence)
    return _clamp_score(10.0 * confidence)


def score_candidate_with_evidence(
    discovery: RawDiscovery,
    *,
    classification: ClassificationResult,
    verification: VerificationResult,
    now: datetime,
    source_type: Optional[SourceType] = None,
) -> ScoreResult:
    """Score one discovery; returns the score plus observable evidence.

    ``classification`` is consumed but unused in Phase 1 (no damping —
    reserved for future cluster-aware scoring). ``verification`` must be
    valid (``validate_verification``) and usable (not DISPUTED/REJECTED);
    violations raise ``ValueError``. ``now`` is injected — this module
    contains no hidden current-time calls.
    """
    if not isinstance(classification, ClassificationResult):
        raise TypeError("classification must be a ClassificationResult")

    if not isinstance(verification, VerificationResult):
        raise ValueError(
            "verification must be a VerificationResult, got "
            f"{type(verification).__name__}"
        )
    validation = validate_verification(verification)
    if not validation["valid"]:
        raise ValueError(
            f"invalid VerificationResult: {validation['issues']}"
        )
    if verification.verification_status in (
        VerificationStatus.DISPUTED,
        VerificationStatus.REJECTED,
    ):
        raise ValueError(
            "verification_status "
            f"{verification.verification_status.value!r} is not scoreable; "
            "filter DISPUTED/REJECTED provenance before scoring"
        )

    matched: List[ScoreRuleMatch] = []
    novelty, age_hours = _novelty(discovery, now=now)
    engagement = _engagement(discovery)
    velocity: Optional[float] = None
    if engagement is not None and age_hours is not None:
        velocity = engagement / max(age_hours, VIRAL_MIN_AGE_HOURS)

    components: Dict[str, float] = {
        "novelty": novelty,
        "practical_utility": _practical_utility(discovery, matched),
        "free_availability": _free_availability(discovery, source_type, matched),
        "audience_interest": _audience_interest(engagement, matched),
        "viral_potential": _viral_potential(engagement, age_hours, matched),
        "credibility": _credibility(verification),
    }

    score = CandidateScore(
        novelty=components["novelty"],
        practical_utility=components["practical_utility"],
        free_availability=components["free_availability"],
        audience_interest=components["audience_interest"],
        viral_potential=components["viral_potential"],
        credibility=components["credibility"],
    )
    return ScoreResult(
        score=score,
        matched_rules=tuple(matched),
        novelty_age_hours=age_hours,
        engagement=engagement,
        velocity=velocity,
    )


def score_candidate(
    discovery: RawDiscovery,
    *,
    classification: ClassificationResult,
    verification: VerificationResult,
    now: datetime,
    source_type: Optional[SourceType] = None,
) -> CandidateScore:
    """Score one discovery deterministically (see module docstring).

    Thin convenience wrapper over ``score_candidate_with_evidence``;
    returns exactly ``score_candidate_with_evidence(...).score``.
    """
    return score_candidate_with_evidence(
        discovery,
        classification=classification,
        verification=verification,
        now=now,
        source_type=source_type,
    ).score


__all__ = [
    "NOVELTY_AGE_BANDS",
    "NOVELTY_OLDER_SCORE",
    "NOVELTY_MISSING_SCORE",
    "UTILITY_RULES",
    "FREE_STRONG_RULES",
    "FREE_MEDIUM_RULES",
    "FREE_WEAK_RULES",
    "FREE_NEGATIVE_RULES",
    "FREE_SOURCE_GITHUB_BONUS",
    "AUDIENCE_CAP_ENGAGEMENT",
    "VIRAL_CAP_VELOCITY",
    "AUDIENCE_MISSING_FLOOR",
    "VIRAL_MISSING_FLOOR",
    "VIRAL_MIN_AGE_HOURS",
    "ScoreRuleMatch",
    "ScoreResult",
    "score_candidate",
    "score_candidate_with_evidence",
]
