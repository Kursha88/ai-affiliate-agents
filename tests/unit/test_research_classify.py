"""Unit tests for the Stage 3.2 deterministic classifier.

Covers the classification contract (explicit ambiguity, zero-signal
state, no silent ``ai_news`` fallback), rule mechanics (phrase vs token
weighting, negative/conflict rules, weak source affinity), determinism
and observability, the false-positive families from the editorial spec,
and structural guarantees (no ``DiscoveryCandidate`` construction, no
network/DB/publishing imports, no ``CLUSTER_PRIORITY`` usage).

All inputs are in-memory ``RawDiscovery`` records; no network access.
"""

from __future__ import annotations

import ast
import inspect
import unittest

from src.domain.strategy import ContentCluster, SourceType
from src.research.adapters.base import RawDiscovery
from src.research.classify import (
    AMBIGUITY_MARGIN,
    MIN_EVIDENCE_SCORE,
    SOURCE_BONUS,
    ClassificationResult,
    classify,
)


def make_discovery(title: str, summary: str = "") -> RawDiscovery:
    """Build a minimal in-memory RawDiscovery for classifier tests."""
    return RawDiscovery(
        title=title,
        url="https://example.com/article",
        source_name="unit_test",
        discovered_at="2026-09-08T12:00:00Z",
        summary=summary,
    )


class TestClearClusterClassification(unittest.TestCase):
    """One clear-cut item per cluster."""

    def _assert_classified(
        self,
        result: ClassificationResult,
        cluster: ContentCluster,
    ) -> None:
        self.assertEqual(result.cluster, cluster)
        self.assertFalse(result.ambiguous)
        self.assertEqual(result.reason, "classified")
        self.assertGreaterEqual(result.scores[cluster], MIN_EVIDENCE_SCORE)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_clear_vibe_coding(self):
        result = classify(
            make_discovery("Show HN: A new AI code editor built for vibe coding")
        )
        self._assert_classified(result, ContentCluster.VIBE_CODING)

    def test_clear_ai_agents(self):
        result = classify(
            make_discovery(
                "A multi-agent framework for building autonomous browser agents"
            )
        )
        self._assert_classified(result, ContentCluster.AI_AGENTS)

    def test_clear_ai_tools(self):
        result = classify(
            make_discovery("An AI tool that turns Figma designs into production code")
        )
        self._assert_classified(result, ContentCluster.AI_TOOLS)

    def test_clear_automation(self):
        result = classify(
            make_discovery(
                "Automate your workflow with this no-code automation platform"
            )
        )
        self._assert_classified(result, ContentCluster.AUTOMATION)

    def test_clear_free_ai(self):
        result = classify(
            make_discovery("Open-source local LLM you can self-host for free")
        )
        self._assert_classified(result, ContentCluster.FREE_AI)

    def test_clear_practical_experiments(self):
        result = classify(
            make_discovery(
                "We tested 12 prompt engineering techniques — here's what actually works"
            )
        )
        self._assert_classified(result, ContentCluster.PRACTICAL_EXPERIMENTS)

    def test_clear_ai_news(self):
        result = classify(
            make_discovery("OpenAI announces GPT-6, topping every benchmark result")
        )
        self._assert_classified(result, ContentCluster.AI_NEWS)


class TestNoSilentFallback(unittest.TestCase):
    """No result may ever silently become ai_news (or any cluster)."""

    def test_zero_signal_returns_no_cluster(self):
        result = classify(
            make_discovery("A deep dive into medieval bread baking traditions")
        )
        self.assertIsNone(result.cluster)
        self.assertFalse(result.ambiguous)
        self.assertEqual(result.reason, "no_signals")
        self.assertEqual(result.confidence, 0.0)

    def test_insufficient_evidence_returns_no_cluster(self):
        result = classify(make_discovery("The agent ecosystem grows"))
        self.assertIsNone(result.cluster)
        self.assertTrue(result.ambiguous)
        self.assertEqual(result.reason, "insufficient_evidence")
        self.assertLess(result.scores[ContentCluster.AI_AGENTS], MIN_EVIDENCE_SCORE)

    def test_ambiguous_margin_returns_no_cluster(self):
        # Spec example: plausibly vibe_coding + ai_agents + free_ai.
        result = classify(make_discovery("Open-source coding agent for VS Code"))
        self.assertIsNone(result.cluster)
        self.assertTrue(result.ambiguous)
        self.assertEqual(result.reason, "ambiguous_margin")
        top_cluster, top_score = sorted(
            result.scores.items(), key=lambda item: (-item[1], item[0].value)
        )[0]
        second_score = sorted(result.scores.values(), reverse=True)[1]
        self.assertEqual(top_cluster, ContentCluster.VIBE_CODING)
        self.assertLess(top_score - second_score, AMBIGUITY_MARGIN)

    def test_ai_news_is_never_the_fallback(self):
        for title in (
            "A deep dive into medieval bread baking traditions",
            "The agent ecosystem grows",
        ):
            result = classify(make_discovery(title))
            self.assertIsNone(result.cluster)
            self.assertEqual(result.scores[ContentCluster.AI_NEWS], 0.0)


class TestSourceAffinity(unittest.TestCase):
    """Source type is a weak bonus, never a classifier on its own."""

    def test_github_source_alone_does_not_imply_free_ai(self):
        result = classify(
            make_discovery("Just shipped my new portfolio website"),
            source_type=SourceType.GITHUB,
        )
        self.assertIsNone(result.cluster)
        self.assertEqual(result.reason, "no_signals")
        self.assertEqual(result.scores[ContentCluster.FREE_AI], 0.0)

    def test_github_source_alone_does_not_imply_vibe_coding(self):
        result = classify(
            make_discovery("Just shipped my new portfolio website"),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.scores[ContentCluster.VIBE_CODING], 0.0)
        self.assertFalse(
            any(match.rule_id == "source_affinity" for match in result.matched_rules)
        )

    def test_official_blog_alone_does_not_imply_ai_news(self):
        result = classify(
            make_discovery("Introducing our new office in Lisbon"),
            source_type=SourceType.OFFICIAL_BLOG,
        )
        self.assertIsNone(result.cluster)
        self.assertEqual(result.scores[ContentCluster.AI_NEWS], 0.0)

    def test_official_blog_affinity_never_satisfies_ai_context_gate(self):
        # A genuine ai_news announcement WITHOUT any AI context text must
        # stay unclassified even with official_blog affinity: source type
        # alone can never open the AI-context gate (Step 4.1).
        result = classify(
            make_discovery("Acme announces a research fellowship program"),
            source_type=SourceType.OFFICIAL_BLOG,
        )
        self.assertIsNone(result.cluster)
        self.assertEqual(result.reason, "no_signals")
        self.assertEqual(result.scores[ContentCluster.AI_NEWS], 0.0)
        self.assertFalse(
            any(match.rule_id == "source_affinity" for match in result.matched_rules)
        )

    def test_source_bonus_applies_only_with_text_evidence(self):
        # Announced + genuine AI context (provider name) => ai_news with
        # the weak official-blog affinity bonus on top.
        result = classify(
            make_discovery("Anthropic announces a research fellowship program"),
            source_type=SourceType.OFFICIAL_BLOG,
        )
        self.assertEqual(result.cluster, ContentCluster.AI_NEWS)
        affinity = [
            match
            for match in result.matched_rules
            if match.rule_id == "source_affinity"
        ]
        self.assertEqual(len(affinity), 1)
        self.assertEqual(affinity[0].cluster, ContentCluster.AI_NEWS)
        self.assertEqual(affinity[0].weight, SOURCE_BONUS)

    def test_github_with_ai_tool_text_stays_ai_tools_not_free_ai(self):
        result = classify(
            make_discovery("An AI tool for generating slide decks, now on GitHub"),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.cluster, ContentCluster.AI_TOOLS)
        self.assertEqual(result.scores[ContentCluster.FREE_AI], 0.0)


class TestRuleMechanics(unittest.TestCase):
    """Phrase weighting, margins, and evidence composition."""

    def test_phrase_match_stronger_than_generic_token(self):
        token_only = classify(make_discovery("Agents are everywhere in the enterprise"))
        self.assertIsNone(token_only.cluster)
        self.assertEqual(token_only.reason, "insufficient_evidence")

        phrase = classify(make_discovery("A new agent framework for Python developers"))
        self.assertEqual(phrase.cluster, ContentCluster.AI_AGENTS)
        self.assertGreater(
            phrase.scores[ContentCluster.AI_AGENTS],
            token_only.scores[ContentCluster.AI_AGENTS],
        )

    def test_mixed_signals_resolved_by_score_and_margin(self):
        result = classify(
            make_discovery(
                "I built a workflow automation tool that syncs my CRM to email"
            )
        )
        self.assertEqual(result.cluster, ContentCluster.AUTOMATION)
        self.assertGreater(
            result.scores[ContentCluster.AUTOMATION],
            result.scores[ContentCluster.PRACTICAL_EXPERIMENTS],
        )
        self.assertGreaterEqual(
            result.scores[ContentCluster.AUTOMATION]
            - result.scores[ContentCluster.PRACTICAL_EXPERIMENTS],
            AMBIGUITY_MARGIN,
        )

    def test_title_and_summary_both_contribute(self):
        title_only = classify(make_discovery("This AI tool writes meeting notes"))
        self.assertEqual(title_only.scores[ContentCluster.AI_TOOLS], 2.5)
        self.assertAlmostEqual(title_only.confidence, 0.25, places=4)  # 2.5/10

        both = classify(
            make_discovery(
                "This AI tool writes meeting notes",
                summary="an AI assistant for weekly recaps",
            )
        )
        self.assertEqual(both.cluster, ContentCluster.AI_TOOLS)
        self.assertEqual(both.scores[ContentCluster.AI_TOOLS], 5.0)
        self.assertAlmostEqual(both.confidence, 0.5, places=4)

    def test_matched_rules_are_observable(self):
        result = classify(
            make_discovery("OpenAI announces GPT-6, topping every benchmark result")
        )
        rule_ids = {match.rule_id for match in result.matched_rules}
        self.assertIn("an_announce", rule_ids)
        self.assertIn("an_model_news", rule_ids)
        self.assertIn("an_benchmark", rule_ids)
        for match in result.matched_rules:
            self.assertEqual(match.cluster, ContentCluster.AI_NEWS)
            self.assertGreater(match.weight, 0.0)

    def test_context_signals_are_observable(self):
        result = classify(
            make_discovery("OpenAI announces GPT-6, topping every benchmark result")
        )
        self.assertIn("ctx_providers", result.context_signals)
        blocked = classify(
            make_discovery("Acme announces a research fellowship program")
        )
        self.assertEqual(blocked.context_signals, ())

    def test_gated_rules_without_context_produce_no_positive_evidence(self):
        # The fellowship title matches an_announce, but the AI-context
        # gate suppresses it entirely -> literally zero positive score.
        result = classify(
            make_discovery("Acme announces a research fellowship program")
        )
        self.assertTrue(all(score == 0.0 for score in result.scores.values()))
        self.assertEqual(result.matched_rules, ())


class TestDeterminism(unittest.TestCase):
    """Same input must always produce the same output."""

    def test_scores_are_deterministic(self):
        discovery = make_discovery(
            "OpenAI announces GPT-6, topping every benchmark result"
        )
        first = classify(discovery)
        second = classify(discovery)
        self.assertEqual(first, second)
        self.assertEqual(first.scores, second.scores)

    def test_confidence_is_deterministic_and_bounded(self):
        discovery = make_discovery("Open-source local LLM you can self-host for free")
        first = classify(discovery)
        second = classify(discovery)
        self.assertEqual(first.confidence, second.confidence)
        for result in (first, second):
            self.assertGreaterEqual(result.confidence, 0.0)
            self.assertLessEqual(result.confidence, 1.0)


class TestTextNormalization(unittest.TestCase):
    """Case-insensitive and Unicode-safe matching."""

    def test_case_insensitivity(self):
        result = classify(
            make_discovery("VIBE CODING Took Over My GitHub Notifications")
        )
        self.assertEqual(result.cluster, ContentCluster.VIBE_CODING)

    def test_unicode_safety(self):
        # Non-breaking spaces fold to plain spaces before matching.
        result = classify(
            make_discovery("A\u00a0local\u00a0model\u00a0for\u00a0every\u00a0developer")
        )
        self.assertEqual(result.cluster, ContentCluster.FREE_AI)

        # Curly quotes are folded, so the rule still matches.
        quoted = classify(make_discovery('The \u201cagentic\u201d future of coding'))
        self.assertTrue(
            any(match.rule_id == "ag_agentic" for match in quoted.matched_rules)
        )


class TestFalsePositives(unittest.TestCase):
    """The misleading-context families from the editorial spec."""

    def test_free_speech_is_not_free_ai(self):
        result = classify(make_discovery("New AI tools for moderating free speech"))
        self.assertNotEqual(result.cluster, ContentCluster.FREE_AI)
        self.assertEqual(result.cluster, ContentCluster.AI_TOOLS)
        self.assertLessEqual(result.scores[ContentCluster.FREE_AI], 0.0)

    def test_free_speech_alone_is_no_signal(self):
        result = classify(
            make_discovery("Free speech policy debates dominate the conference")
        )
        self.assertIsNone(result.cluster)
        self.assertNotEqual(result.cluster, ContentCluster.FREE_AI)

    def test_travel_agent_is_not_ai_agents(self):
        result = classify(make_discovery("New travel agent software for agencies"))
        self.assertIsNone(result.cluster)
        self.assertLess(result.scores[ContentCluster.AI_AGENTS], 0.0)

    def test_industrial_automation_is_not_ai_automation(self):
        result = classify(
            make_discovery("Industrial automation equipment for factories")
        )
        self.assertIsNone(result.cluster)
        self.assertLess(result.scores[ContentCluster.AUTOMATION], 0.0)

    def test_movie_release_date_is_not_ai_news(self):
        result = classify(
            make_discovery("Release date announced for the new Dune movie")
        )
        self.assertIsNone(result.cluster)
        self.assertLess(result.scores[ContentCluster.AI_NEWS], 0.0)


class TestAIContextGate(unittest.TestCase):
    """Step 4.1: generic news/event language requires AI-domain context.

    Regression tests for the observed false positive: 'Acme announces a
    research fellowship program' + official_blog must NOT become ai_news.
    """

    def _assert_not_ai_news(self, title: str) -> ClassificationResult:
        result = classify(
            make_discovery(title), source_type=SourceType.OFFICIAL_BLOG
        )
        self.assertNotEqual(result.cluster, ContentCluster.AI_NEWS)
        self.assertEqual(result.scores[ContentCluster.AI_NEWS], 0.0)
        return result

    # -- generic announcements must NOT become ai_news ------------------

    def test_generic_fellowship_announcement_not_ai_news(self):
        result = self._assert_not_ai_news(
            "Acme announces a research fellowship program"
        )
        self.assertIsNone(result.cluster)
        self.assertEqual(result.reason, "no_signals")

    def test_new_office_announcement_not_ai_news(self):
        result = self._assert_not_ai_news("Company announces new office in London")
        self.assertIsNone(result.cluster)

    def test_employee_program_launch_not_ai_news(self):
        result = self._assert_not_ai_news(
            "Company launches employee wellness program"
        )
        self.assertIsNone(result.cluster)

    def test_conference_registration_not_ai_news(self):
        result = self._assert_not_ai_news("Annual conference registration opens")
        self.assertIsNone(result.cluster)

    def test_movie_release_not_ai_news(self):
        result = classify(make_discovery("Release date announced for the new Dune movie"))
        self.assertIsNone(result.cluster)
        self.assertLess(result.scores[ContentCluster.AI_NEWS], 0.0)

    # -- genuine AI context must remain classifiable as ai_news ---------

    def test_ai_model_announcement_is_ai_news(self):
        result = classify(
            make_discovery("OpenAI announces new reasoning model")
        )
        self.assertEqual(result.cluster, ContentCluster.AI_NEWS)
        self.assertIn("ctx_providers", result.context_signals)

    def test_llm_release_is_ai_news(self):
        result = classify(
            make_discovery("New LLM benchmark results released by independent lab")
        )
        self.assertEqual(result.cluster, ContentCluster.AI_NEWS)
        self.assertIn("ctx_llm", result.context_signals)

    def test_gemini_api_update_is_ai_news(self):
        result = classify(
            make_discovery("Google launches Gemini API update for developers")
        )
        self.assertEqual(result.cluster, ContentCluster.AI_NEWS)
        self.assertIn("ctx_providers", result.context_signals)

    def test_ai_coding_assistant_announcement_classifies(self):
        result = classify(
            make_discovery("Company announces new AI coding assistant for teams")
        )
        # ai_coding_assistant phrase (3.0) beats gated an_announce (2.5).
        self.assertEqual(result.cluster, ContentCluster.VIBE_CODING)
        self.assertIn("ctx_ai", result.context_signals)

    def test_context_in_summary_opens_the_gate(self):
        result = classify(
            make_discovery(
                "Company announces a major research initiative",
                summary="the initiative focuses on artificial intelligence safety",
            )
        )
        self.assertEqual(result.cluster, ContentCluster.AI_NEWS)

    # -- gate integrity ---------------------------------------------------

    def test_source_type_alone_cannot_satisfy_ai_context(self):
        # official_blog affinity contributes at most 0.5 and only to
        # clusters with positive evidence; without text context there is
        # no evidence, so the gate stays closed regardless of source.
        for source_type in SourceType:
            result = classify(
                make_discovery("Company launches employee wellness program"),
                source_type=source_type,
            )
            self.assertIsNone(result.cluster)
            self.assertEqual(result.scores[ContentCluster.AI_NEWS], 0.0)

    def test_non_news_ai_content_is_unaffected_by_the_gate(self):
        # Only ai_news rules are context-gated; other clusters classify
        # exactly as before (no context needed).
        result = classify(make_discovery("A multi-agent framework for Python"))
        self.assertEqual(result.cluster, ContentCluster.AI_AGENTS)
        self.assertEqual(result.context_signals, ())  # gate not even involved


class TestStructuralGuarantees(unittest.TestCase):
    """AST-level guarantees about the classifier module itself."""

    @classmethod
    def _module_tree(cls):
        source = inspect.getsource(classify)
        return ast.parse(source)

    def test_classifier_does_not_construct_discovery_candidate(self):
        tree = self._module_tree()
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attributes = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        self.assertNotIn("DiscoveryCandidate", names)
        self.assertNotIn("DiscoveryCandidate", attributes)

    def test_classifier_has_no_network_db_or_publishing_imports(self):
        tree = self._module_tree()
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        forbidden = {
            "requests",
            "urllib",
            "urllib.request",
            "httpx",
            "aiohttp",
            "socket",
            "http",
            "sqlite3",
            "subprocess",
            "os",
            "pathlib",
            "src.main",
            "src.storage",
            "src.factory",
            "src.agents",
            "src.integrations",
        }
        self.assertFalse(imported & forbidden)

    def test_classifier_does_not_use_cluster_priority(self):
        tree = self._module_tree()
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertNotIn("CLUSTER_PRIORITY", names)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.update(alias.name for alias in node.names)
        self.assertFalse(
            imported & {"CLUSTER_PRIORITY"},
            "CLUSTER_PRIORITY must not even be imported by the classifier",
        )

    def test_result_contract_shape(self):
        result = classify(
            make_discovery("An AI tool that turns Figma designs into production code")
        )
        self.assertIsInstance(result, ClassificationResult)
        payload = result.to_dict()
        self.assertEqual(
            set(payload.keys()),
            {
                "cluster",
                "confidence",
                "scores",
                "matched_rules",
                "ambiguous",
                "reason",
                "context_signals",
            },
        )
        self.assertEqual(payload["cluster"], ContentCluster.AI_TOOLS.value)
        self.assertEqual(
            set(payload["scores"].keys()),
            {cluster.value for cluster in ContentCluster},
        )


if __name__ == "__main__":
    unittest.main()
