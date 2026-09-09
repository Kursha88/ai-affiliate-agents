"""Unit tests for Stage 3.2 deterministic candidate scoring.

Covers the final Step 7 rules: novelty age bands (all boundaries,
missing/invalid/future timestamps), practical-utility rules and cap,
free/open evidence tiers with negative rules ("free speech", "free
trial") and the GitHub-affinity-only-with-evidence guarantee,
log-scaled audience/viral components (floors and caps), the credibility
mapping for VERIFIED/UNVERIFIED with ValueError for DISPUTED/REJECTED
and for invalid VerificationResult, score_candidate ==
score_candidate_with_evidence(...).score, CandidateScore validity,
determinism, no RawDiscovery mutation, and structural guarantees
(no network/DB/ranking/selection imports, no hidden current-time calls,
classify()/verify_provenance() imported but never called).

All inputs are in-memory; no network access.
"""

from __future__ import annotations

import ast
import copy
import inspect
import unittest
from datetime import datetime, timedelta, timezone

from src.domain.strategy import (
    DEFAULT_SCORING_WEIGHTS,
    CandidateScore,
    SourceType,
    VerificationResult,
    VerificationStatus,
    validate_score,
)
from src.research.adapters.base import RawDiscovery
from src.research.classify import ClassificationResult
from src.research.score import (
    AUDIENCE_CAP_ENGAGEMENT,
    AUDIENCE_MISSING_FLOOR,
    NOVELTY_AGE_BANDS,
    ScoreResult,
    VIRAL_CAP_VELOCITY,
    score_candidate,
    score_candidate_with_evidence,
)

NOW = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
PUBLISHED_NOW = NOW.isoformat().replace("+00:00", "Z")


def make_discovery(
    title: str = "Some AI tool",
    url: str | None = "https://example.com/article",
    published_at: str | None = PUBLISHED_NOW,
    raw_score: float | None = None,
    comments_count: int | None = None,
    summary: str = "",
    source_name: str = "hacker_news",
    identifiers: dict | None = None,
    metadata: dict | None = None,
) -> RawDiscovery:
    return RawDiscovery(
        title=title,
        url=url,
        source_name=source_name,
        discovered_at="2026-09-09T12:00:00Z",
        published_at=published_at,
        summary=summary,
        raw_score=raw_score,
        comments_count=comments_count,
        identifiers=identifiers if identifiers is not None else {},
        metadata=metadata if metadata is not None else {},
    )


def make_classification(
    cluster="ai_tools", confidence=0.8, ambiguous=False
) -> ClassificationResult:
    return ClassificationResult(
        cluster=cluster,
        confidence=confidence,
        scores={},
        matched_rules=(),
        ambiguous=ambiguous,
        reason="classified" if cluster else "no_signals",
    )


def make_verification(
    status=VerificationStatus.VERIFIED,
    confidence=0.95,
    primary_source_found=True,
    primary_source_url="https://example.com",
) -> VerificationResult:
    return VerificationResult(
        verification_status=status,
        primary_source_found=primary_source_found,
        primary_source_url=primary_source_url,
        confidence=confidence,
        notes="primary:trusted_official_domain",
    )


def score(discovery: RawDiscovery, **overrides) -> CandidateScore:
    kwargs = {
        "classification": make_classification(),
        "verification": make_verification(),
        "now": NOW,
        "source_type": None,
    }
    kwargs.update(overrides)
    return score_candidate(discovery, **kwargs)


# ══════════════════════════════════════════════════════════════════════
# Novelty
# ══════════════════════════════════════════════════════════════════════


class TestNovelty(unittest.TestCase):
    def _age(self, hours: float) -> RawDiscovery:
        return make_discovery(published_at=(NOW - timedelta(hours=hours)).isoformat().replace("+00:00", "Z"))

    def test_all_boundaries(self):
        cases = {
            0.0: 10.0,
            6.0: 10.0,          # <=6h inclusive upper bound
            6.0001: 8.0,
            24.0: 8.0,
            24.0001: 6.0,
            48.0: 6.0,
            48.0001: 4.0,
            72.0: 4.0,
            72.0001: 2.0,       # older band
            200.0: 2.0,
        }
        for hours, expected in cases.items():
            with self.subTest(hours=hours):
                self.assertEqual(score(self._age(hours)).novelty, expected)

    def test_missing_published_at(self):
        self.assertEqual(score(make_discovery(published_at=None)).novelty, 2.0)

    def test_invalid_published_at(self):
        for bad in ("", "   ", "not-a-timestamp", "2026-13-45T99:00:00Z"):
            with self.subTest(published_at=bad):
                self.assertEqual(score(make_discovery(published_at=bad)).novelty, 2.0)

    def test_future_timestamp_clamps_to_age_zero(self):
        future = make_discovery(
            published_at=(NOW + timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        )
        self.assertEqual(score(future).novelty, 10.0)

    def test_offset_timestamp_accepted(self):
        # "+00:00" offset form (no Z) must parse identically.
        discovery = make_discovery(published_at=(NOW - timedelta(hours=3)).isoformat())
        self.assertEqual(score(discovery).novelty, 10.0)


# ══════════════════════════════════════════════════════════════════════
# Practical utility
# ══════════════════════════════════════════════════════════════════════


class TestPracticalUtility(unittest.TestCase):
    def test_no_match_is_zero(self):
        self.assertEqual(score(make_discovery(title="Quiet river morning")).practical_utility, 0.0)

    def test_single_rules_match(self):
        cases = {
            "How to build an agent": 3.0,
            "A step by step walkthrough": 3.0,  # "tutorial" would add 2.5 (see additive test)
            "Official docs guide": 2.0,
            "Prompts template pack": 2.0,
            "New workflow feature": 2.0,
            "Slack integration released": 2.0,
            "Code example included": 1.5,
            "One-command setup": 1.5,
            "Clean implementation details": 1.5,
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(score(make_discovery(title=title)).practical_utility, expected)

    def test_tutorial_matches(self):
        self.assertEqual(score(make_discovery(title="A great tutorial")).practical_utility, 2.5)

    def test_rules_are_additive_and_capped(self):
        # "step by step" (3.0) + "tutorial" (2.5) = 5.5 — rules stack.
        self.assertEqual(
            score(make_discovery(title="A step by step tutorial")).practical_utility,
            5.5,
        )
        # "how to" (3.0) + "tutorial" (2.5) + "guide" (2.0) + "example" (1.5) = 9.0
        self.assertEqual(
            score(make_discovery(title="How to tutorial guide example")).practical_utility,
            9.0,
        )
        # Cap: far beyond 10 must clamp to exactly 10.
        self.assertEqual(
            score(
                make_discovery(
                    title="How to tutorial guide example setup implementation workflow template"
                )
            ).practical_utility,
            10.0,
        )

    def test_summary_contributes(self):
        result = score(make_discovery(title="Agent toolkit", summary="includes a guide"))
        self.assertGreaterEqual(result.practical_utility, 2.0)

    def test_whole_word_matching_no_substring_false_positive(self):
        # "guide" must not match inside other words on normalized text.
        self.assertEqual(score(make_discovery(title="misguided decisions")).practical_utility, 0.0)


# ══════════════════════════════════════════════════════════════════════
# Free availability
# ══════════════════════════════════════════════════════════════════════


class TestFreeAvailability(unittest.TestCase):
    def test_strong_rules(self):
        for title in ("Open source agent framework", "Open-weights model", "Self-hosted stack"):
            with self.subTest(title=title):
                self.assertGreaterEqual(
                    score(make_discovery(title=title)).free_availability, 3.0
                )

    def test_medium_rules(self):
        for title in ("Generous free tier", "New free plan", "Runs with no api key"):
            with self.subTest(title=title):
                self.assertGreaterEqual(
                    score(make_discovery(title=title)).free_availability, 2.5
                )

    def test_weak_free_rule(self):
        self.assertEqual(score(make_discovery(title="Totally free tool")).free_availability, 1.0)

    def test_free_speech_negative(self):
        # Bare "free" (+1.0) + "free speech" (-3.0) -> 0.0, never negative-ish credit.
        self.assertEqual(score(make_discovery(title="Free speech debate online")).free_availability, 0.0)

    def test_free_trial_negative(self):
        # "free trial" (-2.0) + weak "free" (+1.0) -> 0.0 (clamped).
        self.assertEqual(score(make_discovery(title="Start your free trial today")).free_availability, 0.0)

    def test_negative_only_never_below_zero(self):
        # "free trial" without the bare "free" token firing: clamp at 0.
        self.assertGreaterEqual(
            score(make_discovery(title="Trial limitations explained")).free_availability, 0.0
        )

    def test_github_alone_never_implies_free(self):
        result = score(
            make_discovery(title="Internal registry migration", source_name="github"),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.free_availability, 0.0)

    def test_github_bonus_only_with_positive_evidence(self):
        base = score(make_discovery(title="Open source toolkit"))
        boosted = score(
            make_discovery(title="Open source toolkit", source_name="github"),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(base.free_availability, 3.0)
        self.assertEqual(boosted.free_availability, 3.5)

    def test_cap_at_ten(self):
        self.assertEqual(
            score(make_discovery(title="Open source free tier free plan no api key free")).free_availability,
            10.0,
        )


# ══════════════════════════════════════════════════════════════════════
# Audience interest
# ══════════════════════════════════════════════════════════════════════


class TestAudienceInterest(unittest.TestCase):
    def test_missing_engagement_floor(self):
        self.assertEqual(
            score(make_discovery(raw_score=None, comments_count=None)).audience_interest,
            AUDIENCE_MISSING_FLOOR,
        )

    def test_log_scaling_endpoints(self):
        # At (and beyond) the cap the exact curve reaches 10.0.
        at_cap = score(make_discovery(raw_score=AUDIENCE_CAP_ENGAGEMENT)).audience_interest
        self.assertGreaterEqual(at_cap, 10.0)

        low = score(make_discovery(raw_score=3)).audience_interest
        self.assertGreater(low, 0.0)
        self.assertLess(low, 10.0)

    def test_low_real_engagement_below_missing_evidence_floor(self):
        # Spec-exact curve: a genuinely tiny engagement (1 point) scores
        # below the 3.0 missing-evidence floor — absence of evidence
        # floors at 3.0, weak real evidence does not get the floor.
        self.assertLess(
            score(make_discovery(raw_score=1)).audience_interest,
            AUDIENCE_MISSING_FLOOR,
        )

    def test_cap_beyond_300(self):
        self.assertEqual(score(make_discovery(raw_score=10_000)).audience_interest, 10.0)

    def test_monotonic_in_engagement(self):
        previous = -1.0
        for engagement in (0, 5, 25, 100, 250, 500):
            value = score(make_discovery(raw_score=engagement)).audience_interest
            self.assertGreaterEqual(value, previous)
            previous = value

    def test_comments_used_when_no_raw_score(self):
        self.assertGreater(
            score(make_discovery(comments_count=100)).audience_interest,
            AUDIENCE_MISSING_FLOOR,
        )

    def test_max_of_points_and_comments(self):
        via_points = score(make_discovery(raw_score=100)).audience_interest
        via_comments = score(make_discovery(comments_count=100)).audience_interest
        self.assertAlmostEqual(via_points, via_comments, places=6)

    def test_negative_metrics_ignored(self):
        self.assertEqual(
            score(make_discovery(raw_score=-5, comments_count=-2)).audience_interest,
            AUDIENCE_MISSING_FLOOR,
        )

    def test_zero_engagement_is_real_evidence_not_missing(self):
        # Zero engagement is real (weak) evidence, not MISSING evidence:
        # it takes the exact curve value (~0.0), not the 3.0 floor.
        self.assertLess(
            score(make_discovery(raw_score=0)).audience_interest,
            AUDIENCE_MISSING_FLOOR,
        )


# ══════════════════════════════════════════════════════════════════════
# Viral potential
# ══════════════════════════════════════════════════════════════════════


class TestViralPotential(unittest.TestCase):
    def _with_age(self, hours: float, engagement: float) -> CandidateScore:
        return score(
            make_discovery(
                published_at=(NOW - timedelta(hours=hours)).isoformat().replace("+00:00", "Z"),
                raw_score=engagement,
            )
        )

    def test_missing_engagement_floor(self):
        self.assertEqual(
            score(make_discovery(raw_score=None, comments_count=None)).viral_potential,
            AUDIENCE_MISSING_FLOOR,  # same 3.0 floor constant value
        )

    def test_missing_age_floor(self):
        self.assertEqual(
            score(make_discovery(published_at=None, raw_score=100)).viral_potential,
            AUDIENCE_MISSING_FLOOR,
        )

    def test_velocity_endpoints(self):
        # engagement=100, age=2h -> velocity 50 -> score 10
        self.assertAlmostEqual(self._with_age(2.0, 100).viral_potential, 10.0, places=4)
        # engagement=100, age=0.5h -> velocity 200 -> capped 10
        self.assertEqual(self._with_age(0.25, 100).viral_potential, 10.0)

    def test_age_floor_half_hour(self):
        # age 0.1h clamps to 0.5 -> velocity 100 -> capped 10 (same as 0.5h).
        self.assertEqual(self._with_age(0.1, 25).viral_potential, 10.0)

    def test_low_velocity_below_cap(self):
        value = self._with_age(48.0, 5).viral_potential
        self.assertGreater(value, 0.0)
        self.assertLess(value, 10.0)

    def test_future_age_clamps_raise_velocity(self):
        # Future timestamp -> age 0 -> clamped to 0.5h -> max velocity boost.
        future = score(
            make_discovery(
                published_at=(NOW + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
                raw_score=50,
            )
        )
        self.assertEqual(future.viral_potential, 10.0)

    def test_monotonic_in_velocity(self):
        previous = -1.0
        for hours in (48.0, 24.0, 6.0, 1.0):
            value = self._with_age(hours, 50).viral_potential
            self.assertGreaterEqual(value, previous)
            previous = value


# ══════════════════════════════════════════════════════════════════════
# Credibility
# ══════════════════════════════════════════════════════════════════════


class TestCredibility(unittest.TestCase):
    def test_verified_mapping(self):
        cases = {(0.95, True): 9.75, (0.90, True): 9.5, (0.75, True): 8.75}
        for (confidence, _), expected in cases.items():
            with self.subTest(confidence=confidence):
                self.assertEqual(
                    score(make_discovery(), verification=make_verification(
                        VerificationStatus.VERIFIED, confidence
                    )).credibility,
                    expected,
                )

    def test_unverified_mapping(self):
        for confidence, expected in ((0.35, 3.5), (0.0, 0.0), (0.6, 6.0)):
            with self.subTest(confidence=confidence):
                self.assertEqual(
                    score(make_discovery(), verification=make_verification(
                        VerificationStatus.UNVERIFIED, confidence, False, None
                    )).credibility,
                    expected,
                )

    def test_disputed_raises(self):
        with self.assertRaises(ValueError):
            score(make_discovery(), verification=make_verification(
                VerificationStatus.DISPUTED, 0.0, False, None
            ))

    def test_rejected_raises(self):
        with self.assertRaises(ValueError):
            score(make_discovery(), verification=make_verification(
                VerificationStatus.REJECTED, 0.0, False, None
            ))

    def test_invalid_verification_result_raises(self):
        invalid = [
            VerificationResult(confidence=1.5),                                # out of range
            VerificationResult(primary_source_found=True),                     # missing url
            VerificationResult(
                verification_status=VerificationStatus.VERIFIED,
                primary_source_found=False,
            ),                                                                  # VERIFIED w/o primary
            "not a result",                                                     # wrong type entirely
        ]
        for bad in invalid:
            with self.subTest(repr=bad):
                with self.assertRaises(ValueError):
                    score(make_discovery(), verification=bad)

    def test_verified_beats_unverified_invariant(self):
        verified_low = score(make_discovery(), verification=make_verification(
            VerificationStatus.VERIFIED, 0.75
        )).credibility
        unverified_high = score(make_discovery(), verification=make_verification(
            VerificationStatus.UNVERIFIED, 0.5, False, None
        )).credibility
        self.assertGreater(verified_low, unverified_high)


# ══════════════════════════════════════════════════════════════════════
# Contract, determinism, purity
# ══════════════════════════════════════════════════════════════════════


class TestContractDeterminismPurity(unittest.TestCase):
    def test_score_candidate_equals_evidence_variant(self):
        discovery = make_discovery(
            title="How to self-host an open source model, free tier example",
            raw_score=120,
            comments_count=45,
            published_at=(NOW - timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
        )
        evidence = score_candidate_with_evidence(
            discovery,
            classification=make_classification(),
            verification=make_verification(),
            now=NOW,
        )
        self.assertEqual(
            score_candidate(
                discovery,
                classification=make_classification(),
                verification=make_verification(),
                now=NOW,
            ),
            evidence.score,
        )

    def test_score_result_shape(self):
        evidence = score_candidate_with_evidence(
            make_discovery(raw_score=10),
            classification=make_classification(),
            verification=make_verification(),
            now=NOW,
        )
        self.assertIsInstance(evidence, ScoreResult)
        self.assertEqual(
            set(evidence.__dataclass_fields__),
            {"score", "matched_rules", "novelty_age_hours", "engagement", "velocity", "reason"},
        )
        self.assertEqual(evidence.reason, "scored")
        payload = evidence.to_dict()
        self.assertIn("score", payload)
        self.assertIn("matched_rules", payload)

    def test_candidate_score_components_and_total(self):
        result = score(
            make_discovery(
                title="How to guide",
                raw_score=300,
                published_at=(NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            ),
        )
        self.assertIsInstance(result, CandidateScore)
        expected_total = round(
            sum(
                getattr(result, component) * DEFAULT_SCORING_WEIGHTS[component]
                for component in DEFAULT_SCORING_WEIGHTS
            ),
            4,
        )
        self.assertEqual(result.total_score, expected_total)

    def test_candidate_score_validates(self):
        results = [
            score(make_discovery()),
            # GitHub WITHOUT any free/open evidence in the text: component
            # stays 0.0 (GitHub alone must never imply free).
            score(
                make_discovery(title="Internal registry migration", source_name="github"),
                source_type=SourceType.GITHUB,
            ),
            score(make_discovery(title="free tier tutorial guide", raw_score=1)),
        ]
        for result in results:
            validation = validate_score(result)
            self.assertTrue(validation["valid"], validation["issues"])
            self.assertEqual(validation["issues"], [])

    def test_deterministic_repeated_calls(self):
        discovery = make_discovery(title="Open source free tier guide", raw_score=42)
        kwargs = dict(
            classification=make_classification(),
            verification=make_verification(),
            now=NOW,
        )
        self.assertEqual(
            score_candidate_with_evidence(discovery, **kwargs),
            score_candidate_with_evidence(discovery, **kwargs),
        )

    def test_raw_discovery_not_mutated(self):
        discovery = make_discovery(
            title="How to guide",
            raw_score=10,
            identifiers={"github_repo": "org/tool"},
            metadata={"nested": {"a": [1, 2]}},
        )
        snapshot = copy.deepcopy(discovery)
        score(
            discovery,
            classification=make_classification(),
            verification=make_verification(),
            now=NOW,
        )
        self.assertEqual(discovery, snapshot)

    def test_classification_accepted_but_unused_phase1(self):
        # Any well-formed ClassificationResult must produce identical output.
        discovery = make_discovery(title="Open source guide")
        kwargs = dict(verification=make_verification(), now=NOW)
        baseline = score(discovery, classification=make_classification(), **kwargs)
        for variant in (
            make_classification(cluster=None, confidence=0.0, ambiguous=False),
            make_classification(cluster=None, confidence=0.0, ambiguous=True),
            make_classification(cluster="ai_news", confidence=0.2),
        ):
            self.assertEqual(
                score(discovery, classification=variant, **kwargs),
                baseline,
            )

    def test_wrong_classification_type_rejected(self):
        with self.assertRaises(TypeError):
            score(make_discovery(), classification="classified")


# ══════════════════════════════════════════════════════════════════════
# Structural guarantees (whole module, docstrings stripped)
# ══════════════════════════════════════════════════════════════════════


class TestStructuralGuarantees(unittest.TestCase):
    """AST-level guarantees about the score module's CODE.

    Docstrings are stripped before text scans: the module legitimately
    documents forbidden concepts; the guarantee is that code never uses
    them.
    """

    @classmethod
    def _module_source(cls) -> str:
        from src.research import score as score_module

        return inspect.getsource(score_module)

    @classmethod
    def _code_source(cls) -> str:
        tree = ast.parse(cls._module_source())
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    node.body = body[1:]
        return ast.unparse(tree)

    def _imports(self) -> set:
        imported = set()
        for node in ast.walk(ast.parse(self._module_source())):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        return imported

    def _names(self) -> set:
        return {
            node.id
            for node in ast.walk(ast.parse(self._code_source()))
            if isinstance(node, ast.Name)
        }

    def _calls(self) -> set:
        calls = set()
        for node in ast.walk(ast.parse(self._code_source())):
            if isinstance(node, ast.Call):
                target = node.func
                if isinstance(target, ast.Name):
                    calls.add(target.id)
                elif isinstance(target, ast.Attribute):
                    calls.add(target.attr)
        return calls

    def test_no_network_db_ranking_selection_imports(self):
        imported = self._imports()
        forbidden = {
            "requests", "urllib", "urllib.request", "socket", "http", "httpx",
            "sqlite3", "subprocess", "os", "pathlib", "random",
            "src.main", "src.storage", "src.factory", "src.agents", "src.integrations",
            "src.research.rank", "src.research.select",
        }
        self.assertFalse(imported & forbidden)

    def test_no_hidden_current_time_calls(self):
        source = self._code_source()
        self.assertNotIn("datetime.now", source)
        self.assertNotIn("utcnow", source)
        self.assertEqual(self._calls() & {"now", "utcnow"}, set())

    def test_classify_and_verify_provenance_not_called(self):
        calls = self._calls()
        self.assertNotIn("classify", calls)
        self.assertNotIn("verify_provenance", calls)

    def test_no_cluster_priority_or_selection_constants(self):
        source = self._code_source()
        self.assertNotIn("CLUSTER_PRIORITY", source)
        self.assertNotIn("MIN_CONFIDENCE_FOR_SELECTION", source)

    def test_no_discovery_candidate_or_selection_construction(self):
        names = self._names()
        self.assertNotIn("DiscoveryCandidate", names)
        self.assertNotIn("StrategicSelection", names)

    def test_total_score_never_assigned(self):
        # total_score must remain a computed property: no assignment.
        for node in ast.walk(ast.parse(self._code_source())):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                for target in targets:
                    if isinstance(target, ast.Attribute):
                        self.assertNotEqual(target.attr, "total_score")

    def test_normalization_reused(self):
        self.assertIn("src.research.normalize", self._imports())
        self.assertIn("normalize_title", self._names())


if __name__ == "__main__":
    unittest.main()
