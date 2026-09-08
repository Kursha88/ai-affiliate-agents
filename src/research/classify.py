"""Deterministic first-pass cluster classification (Stage 3.2).

Maps raw discovery text to exactly one ``ContentCluster`` — or an
explicit unclassified/ambiguous result. This is cheap, offline and
fully explainable; an LLM refinement layer may be added later but is
deliberately absent here.

Classification contract (choose-one, documented):

- ``no_signals``:       cluster=None, ambiguous=False, confidence=0.0
                        No positive rule matched at all — a clearly named
                        unclassified state, NOT ambiguity.
- ``insufficient_evidence``:
                        cluster=None, ambiguous=True, confidence=0.0
                        Positive signal exists but the top cluster score
                        is below ``MIN_EVIDENCE_SCORE``.
- ``ambiguous_margin``: cluster=None, ambiguous=True, confidence=0.0
                        Top cluster clears the evidence threshold but the
                        margin over the runner-up is below
                        ``AMBIGUITY_MARGIN``.
- ``classified``:       cluster=<top>, ambiguous=False
                        Top cluster clears the threshold AND the margin.

There is NO fallback to ``ai_news`` (or to any cluster). The classifier
never discards candidates and never constructs ``DiscoveryCandidate`` —
it returns a ``ClassificationResult``; the orchestrator/ranker decides
what happens with unclassified items.

Scoring model (all deterministic, all observable):
- Data-driven rules: ``ClassificationRule(rule_id, cluster, weight,
  patterns)``. Multi-word phrase rules carry higher weight than
  single-token rules. A rule contributes its weight once per text
  segment (title, summary) even if several of its patterns match.
- Negative (conflict) rules subtract weight from a cluster when
  misleading contexts match (``"free speech"``, ``"travel agent"``,
  ``"industrial automation"``, ``"release date"`` …).
- Title and summary are equal-weight text evidence (factor 1.0 each).
  Metadata is NOT used in Phase 1.
- Source affinity is a WEAK bonus (+``SOURCE_BONUS``) applied only to
  clusters that already have positive text evidence. It can never
  classify alone (0.5 < 2.5 threshold).
- ``confidence`` is a normalized rule-strength score:
  ``min(1.0, top_score / CONFIDENCE_SCALE)`` — NOT a probability, and
  zero unless a cluster was assigned.

AI-context gate (Stage 3.2, Step 4.1):

- Generic news/event framing language (``an_announce``,
  ``an_benchmark``, ``an_model_news``) is ``requires_context``-gated:
  it contributes evidence ONLY when at least one AI/domain context
  rule (``AI_CONTEXT_RULES``) matches the document (title or summary).
- Context rules are explicit, conservative patterns: whole-word ``ai``,
  unambiguous phrases (``artificial intelligence``, ``llm``,
  ``machine learning``, ``neural network``, ``inference``,
  ``agentic``, ``reasoning model``, ``ai coding assistant`` …) and
  sufficiently specific model/provider names (``openai``,
  ``anthropic``, ``gemini api``, ``claude model`` …). Bare generic
  words (``model``, ``agent``, ``assistant``) are deliberately NOT
  context signals on their own.
- Context is text-only evidence: ``SourceType`` can never satisfy the
  gate, and the weak source-affinity bonus still applies only to
  clusters that already hold positive text evidence.
- When ONLY gated rules matched (announcement language without any AI
  context), no positive evidence exists → ``no_signals``. Matched
  context rules are observable via ``ClassificationResult.context_signals``.

Editorial priority is deliberately absent: ``CLUSTER_PRIORITY`` belongs
to ranking/tie-breaking, not to classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple

from src.domain.strategy import ContentCluster, SourceType
from src.research.adapters.base import RawDiscovery
from src.research.normalize import normalize_title

# ──────────────────────────────────────────────────────────────────────
# Thresholds and weights (deterministic, documented, test-visible)
# ──────────────────────────────────────────────────────────────────────

#: Top cluster must score at least this much to be assigned.
MIN_EVIDENCE_SCORE: float = 2.5

#: Required margin between the top cluster and the runner-up.
AMBIGUITY_MARGIN: float = 2.0

#: Confidence = min(1.0, top_score / CONFIDENCE_SCALE). Rule-strength
#: normalization, not a probability.
CONFIDENCE_SCALE: float = 10.0

#: Weak source-affinity bonus (applied only where positive evidence exists).
SOURCE_BONUS: float = 0.5


# ──────────────────────────────────────────────────────────────────────
# Rule definitions (data-driven; extend by adding entries, not if/elif)
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClassificationRule:
    """One weighted rule: patterns matched against normalized text.

    ``requires_context`` rules (generic news/event framing language)
    contribute evidence only when at least one AI/domain context rule
    matched the document — see ``AI_CONTEXT_RULES``.
    """

    rule_id: str
    cluster: ContentCluster
    weight: float
    patterns: Tuple[str, ...]
    requires_context: bool = False


@dataclass(frozen=True)
class ContextRule:
    """A domain-context rule: patterns certifying subject-matter context.

    Context rules never contribute score weight. They only open the
    gate for ``requires_context`` rules (see the module docstring).
    """

    rule_id: str
    patterns: Tuple[str, ...]


@dataclass(frozen=True)
class RuleMatch:
    """One matched rule instance (observable evidence)."""

    rule_id: str
    cluster: ContentCluster
    weight: float
    phrase: str


#: Positive rules. Phrase rules (multi-word) > specific tokens > weak tokens.
POSITIVE_RULES: Tuple[ClassificationRule, ...] = (
    # vibe_coding ──────────────────────────────────────────────────────
    ClassificationRule("vc_vibe_coding", ContentCluster.VIBE_CODING, 3.0,
                       ("vibe coding", "vibe-coding")),
    ClassificationRule("vc_ai_coding", ContentCluster.VIBE_CODING, 2.5,
                       ("ai code editor", "ai ide", "ai coding", "code assistant",
                        "coding assistant", "ai pair programming")),
    ClassificationRule("vc_coding_agent", ContentCluster.VIBE_CODING, 2.5,
                       ("coding agent",)),
    ClassificationRule("vc_ai_coding_assistant", ContentCluster.VIBE_CODING, 3.0,
                       ("ai coding assistant", "ai code assistant")),
    ClassificationRule("vc_tools", ContentCluster.VIBE_CODING, 2.0,
                       ("cursor", "windsurf", "cline", "roo code", "aider", "copilot")),
    ClassificationRule("vc_vscode", ContentCluster.VIBE_CODING, 1.5,
                       ("vs code", "vscode")),
    # ai_agents ────────────────────────────────────────────────────────
    ClassificationRule("ag_frameworks", ContentCluster.AI_AGENTS, 2.5,
                       ("agent framework", "autonomous agent", "multi agent",
                        "multi-agent", "ai agent", "agentic ai", "agent orchestration",
                        "llm agent")),
    ClassificationRule("ag_tool_use", ContentCluster.AI_AGENTS, 2.5,
                       ("tool calling", "function calling", "tool use")),
    ClassificationRule("ag_coding_agent_cross", ContentCluster.AI_AGENTS, 2.5,
                       ("coding agent",)),
    ClassificationRule("ag_agentic", ContentCluster.AI_AGENTS, 2.0,
                       ("agentic", "mcp")),
    ClassificationRule("ag_agent_token", ContentCluster.AI_AGENTS, 1.0,
                       ("agent", "agents")),
    # ai_tools ─────────────────────────────────────────────────────────
    ClassificationRule("at_ai_product", ContentCluster.AI_TOOLS, 2.5,
                       ("ai tool", "ai tools", "ai app", "ai platform",
                        "ai service", "ai assistant", "ai product",
                        "productivity ai")),
    ClassificationRule("at_alternative", ContentCluster.AI_TOOLS, 2.0,
                       ("alternative to", "chatbot", "chatbots")),
    # automation ───────────────────────────────────────────────────────
    ClassificationRule("au_workflow", ContentCluster.AUTOMATION, 2.5,
                       ("workflow automation", "no-code automation",
                        "low-code automation", "automate workflow")),
    ClassificationRule("au_platforms", ContentCluster.AUTOMATION, 2.0,
                       ("zapier", "n8n", "make.com")),
    ClassificationRule("au_automation", ContentCluster.AUTOMATION, 1.5,
                       ("automation", "automate", "automating", "automates")),
    ClassificationRule("au_integration", ContentCluster.AUTOMATION, 1.5,
                       ("integration with", "integrates with", "api integration")),
    # free_ai ──────────────────────────────────────────────────────────
    ClassificationRule("fa_open_source", ContentCluster.FREE_AI, 2.5,
                       ("open source", "open-source", "open sourced", "open weights")),
    ClassificationRule("fa_self_hosted", ContentCluster.FREE_AI, 2.5,
                       ("self-hosted", "self hosted", "self-host")),
    ClassificationRule("fa_local", ContentCluster.FREE_AI, 2.5,
                       ("local model", "local llm", "local llms", "run locally",
                        "offline ai", "on-device ai")),
    ClassificationRule("fa_free_tier", ContentCluster.FREE_AI, 2.0,
                       ("free tier", "free plan", "free version", "free alternative",
                        "free ai", "no api key", "for free", "completely free",
                        "100% free")),
    # practical_experiments ────────────────────────────────────────────
    ClassificationRule("pe_experiment", ContentCluster.PRACTICAL_EXPERIMENTS, 3.0,
                       ("experiment", "experimented", "experimenting", "i tested",
                        "we tested", "i tried", "we tried", "hands-on", "hands on")),
    ClassificationRule("pe_compared", ContentCluster.PRACTICAL_EXPERIMENTS, 2.0,
                       ("benchmarked", "compared", "side by side", "real-world test",
                        "real world test", "put it to the test")),
    ClassificationRule("pe_built", ContentCluster.PRACTICAL_EXPERIMENTS, 2.0,
                       ("how i built", "how we built", "i built", "we built")),
    # ai_news ──────────────────────────────────────────────────────────
    # NOTE (Step 4.1): every ai_news rule below is requires_context-gated —
    # announcement/release/benchmark language alone is NOT AI evidence.
    # Verb forms are deliberately "releases"/"released" (not bare
    # "release"); the "release date" trap stays double-guarded by
    # neg_release_date AND the context gate.
    ClassificationRule("an_announce", ContentCluster.AI_NEWS, 2.5,
                       ("announces", "announced", "announcing", "launches",
                        "launched", "releases", "released", "unveils",
                        "unveiled", "acquires", "acquisition", "raises",
                        "funding round", "series a", "lawsuit", "sues",
                        "settlement", "executive order", "policy change",
                        "partners with", "partnership with"),
                       requires_context=True),
    ClassificationRule("an_benchmark", ContentCluster.AI_NEWS, 2.0,
                       ("benchmark result", "tops the benchmark", "tops benchmark",
                        "state of the art"),
                       requires_context=True),
    ClassificationRule("an_model_news", ContentCluster.AI_NEWS, 2.0,
                       ("new model", "gpt-5", "gpt-6"),
                       requires_context=True),
)

#: Negative/conflict rules: subtract weight when misleading contexts match.
NEGATIVE_RULES: Tuple[ClassificationRule, ...] = (
    ClassificationRule("neg_free_speech", ContentCluster.FREE_AI, -3.0,
                       ("free speech", "free expression")),
    ClassificationRule("neg_non_ai_agents", ContentCluster.AI_AGENTS, -3.0,
                       ("travel agent", "travel agency", "insurance agent",
                        "real estate agent", "user agent", "secret agent")),
    ClassificationRule("neg_industrial", ContentCluster.AUTOMATION, -3.0,
                       ("industrial automation", "factory automation",
                        "automation equipment")),
    ClassificationRule("neg_release_date", ContentCluster.AI_NEWS, -3.0,
                       ("release date", "release window", "release calendar",
                        "movie", "film", "trailer", "tv series")),
)

#: Weak source-type affinity. NEVER decisive: 0.5 < MIN_EVIDENCE_SCORE and
#: the bonus is applied only to clusters that already have text evidence.
#: GitHub alone does NOT imply free_ai or vibe_coding; an official blog
#: alone does NOT imply ai_news.
SOURCE_CLUSTER_AFFINITY: Dict[SourceType, FrozenSet[ContentCluster]] = {
    SourceType.GITHUB: frozenset(
        {ContentCluster.VIBE_CODING, ContentCluster.AI_TOOLS, ContentCluster.AI_AGENTS}
    ),
    SourceType.OFFICIAL_BLOG: frozenset({ContentCluster.AI_NEWS}),
    SourceType.OFFICIAL_DOCS: frozenset({ContentCluster.AI_TOOLS}),
}


#: AI/domain context rules (Stage 3.2, Step 4.1). Conservative by design:
#: - whole-word ``ai`` and unambiguous domain phrases;
#: - specific model/provider names only in sufficiently specific forms
#:   (``gemini api`` / ``claude model`` — bare ``claude``/``gemini`` are
#:   also human names / non-AI products);
#: - bare generic words (``model``, ``agent``, ``assistant``) are
#:   deliberately NOT context signals.
AI_CONTEXT_RULES: Tuple[ContextRule, ...] = (
    ContextRule("ctx_ai", ("ai",)),
    ContextRule("ctx_ai_phrases", (
        "artificial intelligence", "generative ai", "genai",
        "machine learning", "deep learning", "neural network", "neural net",
        "language model", "large language model", "foundation model",
        "reasoning model", "ai model", "ai agent", "ai assistant", "ai tool",
        "ai safety", "ai research", "ai startup",
    )),
    ContextRule("ctx_llm", ("llm", "llms")),
    ContextRule("ctx_agentic", ("agentic",)),
    ContextRule("ctx_inference", ("inference",)),
    ContextRule("ctx_open_weights", ("open weights", "open-weights",
                                     "model weights", "local llm")),
    ContextRule("ctx_providers", (
        "openai", "chatgpt", "anthropic", "claude ai", "claude model",
        "claude api", "claude code", "gemini api", "gemini model",
        "google gemini", "google deepmind", "deepmind", "mistral ai",
        "meta ai", "llama model", "deepseek", "qwen", "copilot", "xai",
        "grok ai", "hugging face", "huggingface", "gpt-4", "gpt-5", "gpt-6",
    )),
)


# ──────────────────────────────────────────────────────────────────────
# Matching machinery (compiled once at import; pure and deterministic)
# ──────────────────────────────────────────────────────────────────────


def _compile_pattern(phrase: str) -> re.Pattern:
    """Whole-word regex for a phrase with lightweight plural tolerance.

    Patterns are normalized with the same normalizer as the text, so
    matching is case-insensitive, Unicode-safe and whitespace-stable.
    A trailing ``s?`` is appended when the phrase ends with a letter
    (``"ai tool"`` also matches ``"ai tools"``). Word boundaries are
    ASCII-alnum lookarounds.
    """
    normalized = normalize_title(phrase)
    escaped = re.escape(normalized)
    # Plural tolerance, EXCEPT for very short single tokens: "ai" must
    # not become "ais?" and start matching the nautical word "ais".
    is_short_single_token = " " not in normalized and len(normalized) <= 2
    if escaped and escaped[-1].isalpha() and not is_short_single_token:
        escaped += "s?"
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


_COMPILED_POSITIVE: Tuple[Tuple[ClassificationRule, Tuple[re.Pattern, ...]], ...] = tuple(
    (rule, tuple(_compile_pattern(p) for p in rule.patterns))
    for rule in POSITIVE_RULES
)
_COMPILED_NEGATIVE: Tuple[Tuple[ClassificationRule, Tuple[re.Pattern, ...]], ...] = tuple(
    (rule, tuple(_compile_pattern(p) for p in rule.patterns))
    for rule in NEGATIVE_RULES
)
_COMPILED_CONTEXT: Tuple[Tuple[ContextRule, Tuple[re.Pattern, ...]], ...] = tuple(
    (rule, tuple(_compile_pattern(p) for p in rule.patterns))
    for rule in AI_CONTEXT_RULES
)


def _match_segment(
    text: str,
    compiled: Tuple[Tuple[ClassificationRule, Tuple[re.Pattern, ...]], ...],
    context_present: bool = True,
) -> List[RuleMatch]:
    """Match every rule against one text segment (weight once per rule).

    ``requires_context`` rules are skipped unless ``context_present``.
    """
    matches: List[RuleMatch] = []
    if not text:
        return matches
    for rule, patterns in compiled:
        if rule.requires_context and not context_present:
            continue
        for pattern, compiled_pattern in zip(rule.patterns, patterns):
            if compiled_pattern.search(text):
                matches.append(
                    RuleMatch(rule.rule_id, rule.cluster, rule.weight, pattern)
                )
                break  # one contribution per rule per segment
    return matches


def _context_signals(title_text: str, summary_text: str) -> Tuple[str, ...]:
    """Ids of matched AI/domain context rules, in defined order."""
    found: List[str] = []
    for rule, patterns in _COMPILED_CONTEXT:
        for pattern, compiled_pattern in zip(rule.patterns, patterns):
            if compiled_pattern.search(title_text) or compiled_pattern.search(
                summary_text
            ):
                found.append(rule.rule_id)
                break
    return tuple(found)


# ──────────────────────────────────────────────────────────────────────
# Result object
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClassificationResult:
    """Outcome of classifying one raw discovery.

    ``cluster`` is ``None`` unless a cluster was confidently assigned.
    ``scores`` covers every cluster (0.0 included) so decisions are
    fully inspectable. ``matched_rules`` lists the concrete evidence
    (positive matches, source affinity, negative matches) in
    deterministic order.
    """

    cluster: Optional[ContentCluster]
    confidence: float
    scores: Dict[ContentCluster, float]
    matched_rules: Tuple[RuleMatch, ...]
    ambiguous: bool
    reason: str
    context_signals: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, object]:
        return {
            "cluster": self.cluster.value if self.cluster else None,
            "confidence": self.confidence,
            "scores": {cluster.value: score for cluster, score in self.scores.items()},
            "context_signals": list(self.context_signals),
            "matched_rules": [
                {
                    "rule_id": match.rule_id,
                    "cluster": match.cluster.value,
                    "weight": match.weight,
                    "phrase": match.phrase,
                }
                for match in self.matched_rules
            ],
            "ambiguous": self.ambiguous,
            "reason": self.reason,
        }


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def classify(
    discovery: RawDiscovery,
    source_type: Optional[SourceType] = None,
) -> ClassificationResult:
    """Classify one raw discovery deterministically.

    ``source_type`` is optional and weak: the orchestrator passes the
    adapter's source type; ``None`` (default) skips the affinity bonus
    entirely. Source affinity alone can never classify a candidate.
    """
    title_text = normalize_title(discovery.title)
    summary_text = normalize_title(discovery.summary)

    # AI/domain context gate: context-gated rules contribute evidence
    # only when at least one context rule matched (see module docstring).
    context_signals = _context_signals(title_text, summary_text)
    context_present = bool(context_signals)

    positive_matches = _match_segment(title_text, _COMPILED_POSITIVE, context_present)
    positive_matches += _match_segment(
        summary_text, _COMPILED_POSITIVE, context_present
    )
    negative_matches = _match_segment(title_text, _COMPILED_NEGATIVE)
    negative_matches += _match_segment(summary_text, _COMPILED_NEGATIVE)

    scores: Dict[ContentCluster, float] = {
        cluster: 0.0 for cluster in ContentCluster
    }
    for match in positive_matches:
        scores[match.cluster] += match.weight

    # Weak source affinity: only where positive text evidence exists.
    matched_rules: List[RuleMatch] = list(positive_matches)
    if source_type is not None:
        for cluster in sorted(
            SOURCE_CLUSTER_AFFINITY.get(source_type, frozenset()),
            key=lambda cluster: cluster.value,
        ):
            if scores[cluster] > 0.0:
                scores[cluster] += SOURCE_BONUS
                matched_rules.append(
                    RuleMatch("source_affinity", cluster, SOURCE_BONUS, source_type.value)
                )

    for match in negative_matches:
        scores[match.cluster] += match.weight
    matched_rules += negative_matches

    scores = {cluster: round(score, 4) for cluster, score in scores.items()}

    if not positive_matches:
        return ClassificationResult(
            cluster=None,
            confidence=0.0,
            scores=scores,
            matched_rules=tuple(matched_rules),
            ambiguous=False,
            reason="no_signals",
            context_signals=context_signals,
        )

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0].value))
    top_cluster, top_score = ranked[0]
    second_score = ranked[1][1]

    if top_score < MIN_EVIDENCE_SCORE:
        return ClassificationResult(
            cluster=None,
            confidence=0.0,
            scores=scores,
            matched_rules=tuple(matched_rules),
            ambiguous=True,
            reason="insufficient_evidence",
            context_signals=context_signals,
        )

    if (top_score - second_score) < AMBIGUITY_MARGIN:
        return ClassificationResult(
            cluster=None,
            confidence=0.0,
            scores=scores,
            matched_rules=tuple(matched_rules),
            ambiguous=True,
            reason="ambiguous_margin",
            context_signals=context_signals,
        )

    return ClassificationResult(
        cluster=top_cluster,
        confidence=round(min(1.0, max(top_score, 0.0) / CONFIDENCE_SCALE), 4),
        scores=scores,
        matched_rules=tuple(matched_rules),
        ambiguous=False,
        reason="classified",
        context_signals=context_signals,
    )


__all__ = [
    "MIN_EVIDENCE_SCORE",
    "AMBIGUITY_MARGIN",
    "CONFIDENCE_SCALE",
    "SOURCE_BONUS",
    "POSITIVE_RULES",
    "NEGATIVE_RULES",
    "SOURCE_CLUSTER_AFFINITY",
    "AI_CONTEXT_RULES",
    "ContextRule",
    "ClassificationRule",
    "RuleMatch",
    "ClassificationResult",
    "classify",
]
