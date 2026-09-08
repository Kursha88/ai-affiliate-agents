"""Content strategy domain contracts for the Content Intelligence Engine.

Stage 3.1 — schema/contracts ONLY. No scoring logic, no researcher or
strategist agents, no persistence. Future stages build on these types.

Intelligence pipeline this schema models:

    DISCOVER -> VERIFY -> SCORE -> SELECT -> RESEARCH / EXPERIMENT ->
    CREATE CONTENT CLUSTER -> ADAPT PER PLATFORM -> PUBLISH -> TRACK -> LEARN

Design invariants (Stage 3.1 decisions):

1. Explicit classification only.
   ``DiscoveryCandidate.source_type`` and ``.content_cluster`` have NO
   defaults, and ``from_dict()`` raises ``ValueError`` on unknown enum
   values. A classification failure must never silently turn into a
   default cluster (``ai_news`` or any other).

2. ``CLUSTER_PRIORITY`` is editorial DATA, not a selection algorithm.
   Future topic selection must combine candidate quality, novelty,
   practical utility, credibility, audience interest, viral potential,
   free availability, and cluster/editorial weighting. ``ai_news`` is
   demoted in editorial priority, but high-quality breaking AI news
   must remain selectable.

3. ``CandidateScore.total_score`` is a deterministic computed property.
   Component scores are the single source of truth; the total is always
   derived from ``DEFAULT_SCORING_WEIGHTS``. Any stored/serialized
   ``total_score`` value is ignored on deserialization, so components
   and total can never disagree.

4. No persistence coupling.
   These models never touch ``data/factory.db``, ``StateService`` or
   repositories. ``content_id`` fields are soft links to the existing
   ``ContentItem`` aggregate for future stages; no foreign key, no
   schema change, no migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────


class ContentCluster(StrEnum):
    """Primary editorial content clusters (Stage 3.1 editorial direction)."""

    VIBE_CODING = "vibe_coding"
    AI_AGENTS = "ai_agents"
    AI_TOOLS = "ai_tools"
    AUTOMATION = "automation"
    FREE_AI = "free_ai"
    PRACTICAL_EXPERIMENTS = "practical_experiments"
    AI_NEWS = "ai_news"  # supported, but no longer dominant/default


class ContentFormat(StrEnum):
    """Content formats the strategy layer may recommend for a topic."""

    BREAKING_NEWS = "breaking_news"
    TOOL_DISCOVERY = "tool_discovery"
    PRACTICAL_GUIDE = "practical_guide"
    COMPARISON = "comparison"
    EXPERIMENT = "experiment"
    WORKFLOW = "workflow"
    PROMPT = "prompt"
    CASE_STUDY = "case_study"
    OPINION_ANALYSIS = "opinion_analysis"
    ROUNDUP = "roundup"


class SourceType(StrEnum):
    """Discovery source types (explicit classification required)."""

    HACKER_NEWS = "hacker_news"
    REDDIT = "reddit"
    GITHUB = "github"
    OFFICIAL_BLOG = "official_blog"
    OFFICIAL_DOCS = "official_docs"
    PRODUCT_HUNT = "product_hunt"
    X = "x"
    OTHER = "other"


class TargetPlatform(StrEnum):
    """Platforms a selected topic may later be adapted into."""

    TELEGRAM = "telegram"
    X = "x"
    LINKEDIN = "linkedin"
    REDDIT = "reddit"
    YOUTUBE_SHORTS = "youtube_shorts"
    TIKTOK = "tiktok"
    PINTEREST = "pinterest"


class VerificationStatus(StrEnum):
    """Outcome of the VERIFY stage for a discovery candidate."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    REJECTED = "rejected"


class PackageVariantStatus(StrEnum):
    """Lifecycle of one platform-native variant inside a ContentPackage."""

    PLANNED = "planned"
    DRAFTED = "drafted"
    APPROVED = "approved"
    PUBLISHED = "published"
    SKIPPED = "skipped"


class CandidateStage(StrEnum):
    """Position of a candidate in the intelligence pipeline."""

    DISCOVERED = "discovered"
    VERIFIED = "verified"
    SCORED = "scored"
    SELECTED = "selected"
    RESEARCH_EXPERIMENT = "research_experiment"
    CONTENT_CLUSTER = "content_cluster"
    PLATFORM_ADAPTATION = "platform_adaptation"
    PUBLISHED = "published"
    TRACKED = "tracked"
    LEARNED = "learned"


# ──────────────────────────────────────────────────────────────────────
# Strategy constants (editorial DATA, not logic)
# ──────────────────────────────────────────────────────────────────────

#: Names of the CandidateScore components, in canonical order.
SCORE_COMPONENTS: Tuple[str, ...] = (
    "novelty",
    "practical_utility",
    "free_availability",
    "audience_interest",
    "viral_potential",
    "credibility",
)

#: Inclusive bounds for every individual score component.
SCORE_MIN: float = 0.0
SCORE_MAX: float = 10.0

#:
#: Deterministic weights used to compute ``CandidateScore.total_score``.
#: Keys correspond 1:1 to ``SCORE_COMPONENTS`` and the values sum to 1.0.
#: Practical utility and free availability are weighted highest, matching
#: the editorial positioning (practical, accessible, hands-on content).
#:
DEFAULT_SCORING_WEIGHTS: Dict[str, float] = {
    "novelty": 0.15,
    "practical_utility": 0.25,
    "free_availability": 0.20,
    "audience_interest": 0.15,
    "viral_potential": 0.10,
    "credibility": 0.15,
}

#:
#: Editorial cluster priority (highest first). DATA ONLY — future topic
#: selection must NOT simply pick the first cluster. Selection is expected
#: to combine:
#:   - candidate quality
#:   - novelty
#:   - practical utility
#:   - credibility
#:   - audience interest
#:   - viral potential
#:   - free availability
#:   - cluster/editorial weighting
#:
#: ``ai_news`` is intentionally LAST: it is demoted editorially so it can
#: no longer be the dominant/default content type, but it remains fully
#: selectable when a candidate scores high on quality and credibility.
#:
CLUSTER_PRIORITY: Tuple[ContentCluster, ...] = (
    ContentCluster.VIBE_CODING,
    ContentCluster.AI_AGENTS,
    ContentCluster.AI_TOOLS,
    ContentCluster.AUTOMATION,
    ContentCluster.FREE_AI,
    ContentCluster.PRACTICAL_EXPERIMENTS,
    ContentCluster.AI_NEWS,
)

#: Minimum VerificationResult.confidence for a candidate to be eligible
#: for selection. Data constant consumed by future selection logic.
MIN_CONFIDENCE_FOR_SELECTION: float = 0.7


# ──────────────────────────────────────────────────────────────────────
# Deserialization helpers (strict on purpose — see design invariant 1)
# ──────────────────────────────────────────────────────────────────────


def _require(data: Dict[str, Any], key: str, model: str) -> Any:
    if key not in data or data[key] is None:
        raise ValueError(f"{model}.from_dict: missing required field '{key}'")
    return data[key]


def _coerce_enum(value: Any, enum_cls: type, field_name: str) -> Any:
    """Coerce a raw value to an enum member, strictly.

    Accepts an enum instance or its exact string value. Raises
    ValueError on anything else — classification failures must never
    silently become a default.
    """
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise ValueError(
                f"Unknown {enum_cls.__name__} value for '{field_name}': {value!r} "
                f"(explicit classification required — no silent defaults)"
            ) from exc
    raise ValueError(
        f"Invalid {enum_cls.__name__} for '{field_name}': {value!r}"
    )


def _coerce_bool(value: Any, key: str, model: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{model}.{key} must be a bool, got {value!r}")


def _coerce_float(value: Any, key: str, model: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{model}.{key} must be a number, got {value!r}")
    return float(value)


def _coerce_opt_float(value: Any, key: str, model: str) -> Optional[float]:
    return None if value is None else _coerce_float(value, key, model)


# ──────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DiscoveryCandidate:
    """A raw discovered topic (DISCOVER stage).

    ``source_type`` and ``content_cluster`` are REQUIRED — they must be
    explicitly assigned/classified at construction time and carry no
    silent defaults.
    """

    candidate_id: str
    title: str
    source_type: SourceType
    source_url: str
    discovered_at: str  # ISO-8601 UTC string
    content_cluster: ContentCluster

    source_name: str = ""
    published_at: Optional[str] = None  # ISO-8601 UTC string, if known
    summary: str = ""
    raw_score: Optional[float] = None  # platform-native score (HN points etc.)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "source_type": self.source_type.value,
            "source_url": self.source_url,
            "discovered_at": self.discovered_at,
            "content_cluster": self.content_cluster.value,
            "source_name": self.source_name,
            "published_at": self.published_at,
            "summary": self.summary,
            "raw_score": self.raw_score,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveryCandidate":
        return cls(
            candidate_id=str(_require(data, "candidate_id", cls.__name__)),
            title=str(_require(data, "title", cls.__name__)),
            source_type=_coerce_enum(
                _require(data, "source_type", cls.__name__), SourceType, "source_type"
            ),
            source_url=str(_require(data, "source_url", cls.__name__)),
            discovered_at=str(_require(data, "discovered_at", cls.__name__)),
            content_cluster=_coerce_enum(
                _require(data, "content_cluster", cls.__name__),
                ContentCluster,
                "content_cluster",
            ),
            source_name=str(data.get("source_name", "")),
            published_at=data.get("published_at"),
            summary=str(data.get("summary", "")),
            raw_score=_coerce_opt_float(data.get("raw_score"), "raw_score", cls.__name__),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of the VERIFY stage for a candidate."""

    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    primary_source_found: bool = False
    primary_source_url: Optional[str] = None
    confidence: float = 0.0  # 0.0 .. 1.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verification_status": self.verification_status.value,
            "primary_source_found": self.primary_source_found,
            "primary_source_url": self.primary_source_url,
            "confidence": self.confidence,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationResult":
        return cls(
            verification_status=_coerce_enum(
                data.get("verification_status", VerificationStatus.UNVERIFIED),
                VerificationStatus,
                "verification_status",
            ),
            primary_source_found=_coerce_bool(
                data.get("primary_source_found", False),
                "primary_source_found",
                cls.__name__,
            ),
            primary_source_url=data.get("primary_source_url"),
            confidence=_coerce_float(data.get("confidence", 0.0), "confidence", cls.__name__),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class CandidateScore:
    """SCORE stage output.

    The six component scores are the single source of truth.
    ``total_score`` is a deterministic computed property derived from
    ``DEFAULT_SCORING_WEIGHTS`` — it is never stored, supplied, or
    deserialized, so components and total can never disagree.
    """

    novelty: float
    practical_utility: float
    free_availability: float
    audience_interest: float
    viral_potential: float
    credibility: float

    @property
    def total_score(self) -> float:
        """Deterministic weighted total derived from the components."""
        return round(
            sum(
                getattr(self, component) * DEFAULT_SCORING_WEIGHTS[component]
                for component in SCORE_COMPONENTS
            ),
            4,
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            component: getattr(self, component) for component in SCORE_COMPONENTS
        }
        # Included for observability only; ignored by from_dict().
        data["total_score"] = self.total_score
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateScore":
        # A stored "total_score" key is intentionally ignored: the total is
        # always recomputed from the components (design invariant 3).
        return cls(
            **{
                component: _coerce_float(
                    _require(data, component, cls.__name__), component, cls.__name__
                )
                for component in SCORE_COMPONENTS
            }
        )


@dataclass(frozen=True)
class StrategicSelection:
    """SELECT stage output for a candidate."""

    selected: bool
    selection_reason: str = ""
    recommended_format: Optional[ContentFormat] = None
    target_platforms: Tuple[TargetPlatform, ...] = ()
    research_required: bool = False
    experiment_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected": self.selected,
            "selection_reason": self.selection_reason,
            "recommended_format": (
                self.recommended_format.value if self.recommended_format else None
            ),
            "target_platforms": [p.value for p in self.target_platforms],
            "research_required": self.research_required,
            "experiment_required": self.experiment_required,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategicSelection":
        platforms_raw = data.get("target_platforms", [])
        return cls(
            selected=_coerce_bool(
                _require(data, "selected", cls.__name__), "selected", cls.__name__
            ),
            selection_reason=str(data.get("selection_reason", "")),
            recommended_format=(
                _coerce_enum(data["recommended_format"], ContentFormat, "recommended_format")
                if data.get("recommended_format") is not None
                else None
            ),
            target_platforms=tuple(
                _coerce_enum(p, TargetPlatform, "target_platforms") for p in platforms_raw
            ),
            research_required=_coerce_bool(
                data.get("research_required", False), "research_required", cls.__name__
            ),
            experiment_required=_coerce_bool(
                data.get("experiment_required", False), "experiment_required", cls.__name__
            ),
        )


@dataclass(frozen=True)
class ContentCandidate:
    """Aggregate binding discovery, verification, scoring and selection.

    ``stage`` tracks the candidate's position in the intelligence
    pipeline. ``content_id`` is a soft forward link to the existing
    ``ContentItem`` aggregate (set once content generation produced a
    persisted ContentItem) — deliberately Optional with no foreign key
    and no database coupling.
    """

    candidate: DiscoveryCandidate
    verification: VerificationResult = field(default_factory=VerificationResult)
    score: Optional[CandidateScore] = None
    selection: Optional[StrategicSelection] = None
    stage: CandidateStage = CandidateStage.DISCOVERED
    content_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "verification": self.verification.to_dict(),
            "score": self.score.to_dict() if self.score else None,
            "selection": self.selection.to_dict() if self.selection else None,
            "stage": self.stage.value,
            "content_id": self.content_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentCandidate":
        candidate_data = _require(data, "candidate", cls.__name__)
        if not isinstance(candidate_data, dict):
            raise ValueError(f"{cls.__name__}.candidate must be a dict")
        score_data = data.get("score")
        selection_data = data.get("selection")
        return cls(
            candidate=DiscoveryCandidate.from_dict(candidate_data),
            verification=(
                VerificationResult.from_dict(data["verification"])
                if data.get("verification")
                else VerificationResult()
            ),
            score=CandidateScore.from_dict(score_data) if score_data else None,
            selection=StrategicSelection.from_dict(selection_data) if selection_data else None,
            stage=_coerce_enum(
                data.get("stage", CandidateStage.DISCOVERED), CandidateStage, "stage"
            ),
            content_id=data.get("content_id"),
        )


@dataclass(frozen=True)
class PlatformVariant:
    """One platform-native variant slot of a ContentPackage (schema only).

    Stage 3.1 defines the contract; generation/adaptation logic arrives
    in a later stage.
    """

    platform: TargetPlatform
    status: PackageVariantStatus = PackageVariantStatus.PLANNED
    scheduled_at: Optional[str] = None  # ISO-8601 UTC string
    published_at: Optional[str] = None  # ISO-8601 UTC string
    external_post_id: Optional[str] = None
    post_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform.value,
            "status": self.status.value,
            "scheduled_at": self.scheduled_at,
            "published_at": self.published_at,
            "external_post_id": self.external_post_id,
            "post_url": self.post_url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlatformVariant":
        return cls(
            platform=_coerce_enum(
                _require(data, "platform", cls.__name__), TargetPlatform, "platform"
            ),
            status=_coerce_enum(
                data.get("status", PackageVariantStatus.PLANNED),
                PackageVariantStatus,
                "status",
            ),
            scheduled_at=data.get("scheduled_at"),
            published_at=data.get("published_at"),
            external_post_id=data.get("external_post_id"),
            post_url=data.get("post_url"),
        )


@dataclass(frozen=True)
class ContentPackage:
    """One selected topic expanded into platform-native variants.

    A single selected candidate may produce variants for telegram, x,
    linkedin, reddit, youtube_shorts, tiktok and pinterest. Stage 3.1
    defines only this container contract.
    """

    package_id: str
    candidate_id: str
    variants: Tuple[PlatformVariant, ...] = ()
    content_id: Optional[str] = None  # soft link to ContentItem
    created_at: Optional[str] = None  # ISO-8601 UTC string

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_id": self.package_id,
            "candidate_id": self.candidate_id,
            "variants": [v.to_dict() for v in self.variants],
            "content_id": self.content_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentPackage":
        variants_raw = data.get("variants", [])
        if not isinstance(variants_raw, (list, tuple)):
            raise ValueError(f"{cls.__name__}.variants must be a list")
        return cls(
            package_id=str(_require(data, "package_id", cls.__name__)),
            candidate_id=str(_require(data, "candidate_id", cls.__name__)),
            variants=tuple(PlatformVariant.from_dict(v) for v in variants_raw),
            content_id=data.get("content_id"),
            created_at=data.get("created_at"),
        )


# ──────────────────────────────────────────────────────────────────────
# Validators (pure functions; repo-wide {"valid", "issues"} contract)
# ──────────────────────────────────────────────────────────────────────


def validate_candidate(candidate: DiscoveryCandidate) -> Dict[str, Any]:
    """Validate a DiscoveryCandidate; returns {"valid", "issues"}."""
    issues: List[str] = []

    if not candidate.candidate_id or not candidate.candidate_id.strip():
        issues.append("candidate_id is empty")
    if not candidate.title or not candidate.title.strip():
        issues.append("title is empty")
    if not isinstance(candidate.source_type, SourceType):
        issues.append("source_type must be an explicit SourceType")
    if not isinstance(candidate.content_cluster, ContentCluster):
        issues.append("content_cluster must be an explicit ContentCluster")
    url = candidate.source_url or ""
    if not url.strip():
        issues.append("source_url is empty")
    elif not (url.startswith("http://") or url.startswith("https://")):
        issues.append("source_url must be an absolute http(s) URL")
    if not candidate.discovered_at or not candidate.discovered_at.strip():
        issues.append("discovered_at is empty")

    return {"valid": len(issues) == 0, "issues": issues}


def validate_verification(verification: VerificationResult) -> Dict[str, Any]:
    """Validate a VerificationResult; returns {"valid", "issues"}."""
    issues: List[str] = []

    if not isinstance(verification.verification_status, VerificationStatus):
        issues.append("verification_status must be a VerificationStatus")

    confidence = verification.confidence
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        issues.append("confidence must be a number")
    elif not (0.0 <= float(confidence) <= 1.0):
        issues.append(f"confidence out of range 0..1: {confidence}")

    if verification.primary_source_found:
        if not (verification.primary_source_url or "").strip():
            issues.append("primary_source_found=True requires primary_source_url")
    if (
        verification.verification_status == VerificationStatus.VERIFIED
        and not verification.primary_source_found
    ):
        issues.append("status VERIFIED requires primary_source_found=True")

    return {"valid": len(issues) == 0, "issues": issues}


def validate_score(score: CandidateScore) -> Dict[str, Any]:
    """Validate component scores; returns {"valid", "issues", "total_score"}.

    total_score is included for observability; it is always the
    deterministic value computed from the components.
    """
    issues: List[str] = []

    for component in SCORE_COMPONENTS:
        value = getattr(score, component)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            issues.append(f"{component} must be a number")
        elif not (SCORE_MIN <= float(value) <= SCORE_MAX):
            issues.append(f"{component} out of range {SCORE_MIN}..{SCORE_MAX}: {value}")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "total_score": score.total_score,
    }


def validate_selection(selection: StrategicSelection) -> Dict[str, Any]:
    """Validate a StrategicSelection; returns {"valid", "issues"}."""
    issues: List[str] = []

    if not isinstance(selection.selected, bool):
        issues.append("selected must be a bool")

    if (
        isinstance(selection.recommended_format, ContentFormat)
        or selection.recommended_format is None
    ):
        pass
    else:
        issues.append("recommended_format must be a ContentFormat or None")

    platforms = selection.target_platforms
    if not isinstance(platforms, tuple):
        issues.append("target_platforms must be a tuple of TargetPlatform")
    else:
        for platform in platforms:
            if not isinstance(platform, TargetPlatform):
                issues.append(f"unknown target platform: {platform!r}")

    if selection.selected:
        if not selection.selection_reason.strip():
            issues.append("selected=True requires a selection_reason")
        if not platforms:
            issues.append("selected=True requires at least one target platform")

    return {"valid": len(issues) == 0, "issues": issues}


__all__ = [
    "ContentCluster",
    "ContentFormat",
    "SourceType",
    "TargetPlatform",
    "VerificationStatus",
    "PackageVariantStatus",
    "CandidateStage",
    "SCORE_COMPONENTS",
    "SCORE_MIN",
    "SCORE_MAX",
    "DEFAULT_SCORING_WEIGHTS",
    "CLUSTER_PRIORITY",
    "MIN_CONFIDENCE_FOR_SELECTION",
    "DiscoveryCandidate",
    "VerificationResult",
    "CandidateScore",
    "StrategicSelection",
    "ContentCandidate",
    "PlatformVariant",
    "ContentPackage",
    "validate_candidate",
    "validate_verification",
    "validate_score",
    "validate_selection",
]
