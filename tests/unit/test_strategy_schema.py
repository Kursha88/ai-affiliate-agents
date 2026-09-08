"""Unit tests for the Stage 3.1 strategy contract layer (src/domain/strategy.py).

Coverage scope: enum definitions, explicit classification, deterministic
scoring, serialization round-trips, validation rules, editorial data
invariants, frozen dataclasses, ContentPackage platform coverage and
soft-link behavior.

Out of scope by design: lifecycle transitions, DB persistence, SQLite
migrations, production orchestration, Researcher/Strategist behavior,
platform publishing.
"""

import unittest
from dataclasses import FrozenInstanceError

from src.domain.strategy import (
    DEFAULT_SCORING_WEIGHTS,
    MIN_CONFIDENCE_FOR_SELECTION,
    SCORE_COMPONENTS,
    CLUSTER_PRIORITY,
    CandidateScore,
    CandidateStage,
    ContentCandidate,
    ContentCluster,
    ContentFormat,
    ContentPackage,
    DiscoveryCandidate,
    PackageVariantStatus,
    PlatformVariant,
    SourceType,
    StrategicSelection,
    TargetPlatform,
    VerificationResult,
    VerificationStatus,
    validate_candidate,
    validate_score,
    validate_selection,
    validate_verification,
)


def make_candidate(**overrides) -> DiscoveryCandidate:
    """Valid DiscoveryCandidate factory (explicit classification, no defaults)."""
    base = dict(
        candidate_id="cand-1",
        title="New open-source vibe coding tool",
        source_type=SourceType.GITHUB,
        source_url="https://github.com/example/vibe-tool",
        discovered_at="2026-09-08T10:00:00Z",
        content_cluster=ContentCluster.VIBE_CODING,
    )
    base.update(overrides)
    return DiscoveryCandidate(**base)


def make_score(**overrides) -> CandidateScore:
    base = dict(
        novelty=8.0,
        practical_utility=9.0,
        free_availability=7.0,
        audience_interest=6.0,
        viral_potential=5.0,
        credibility=9.0,
    )
    base.update(overrides)
    return CandidateScore(**base)


class TestEnumDefinitions(unittest.TestCase):
    def test_content_cluster_members(self) -> None:
        self.assertEqual(
            [c.value for c in ContentCluster],
            [
                "vibe_coding",
                "ai_agents",
                "ai_tools",
                "automation",
                "free_ai",
                "practical_experiments",
                "ai_news",
            ],
        )

    def test_content_format_members(self) -> None:
        self.assertEqual(
            [f.value for f in ContentFormat],
            [
                "breaking_news",
                "tool_discovery",
                "practical_guide",
                "comparison",
                "experiment",
                "workflow",
                "prompt",
                "case_study",
                "opinion_analysis",
                "roundup",
            ],
        )

    def test_source_type_members(self) -> None:
        self.assertEqual(
            [s.value for s in SourceType],
            [
                "hacker_news",
                "reddit",
                "github",
                "official_blog",
                "official_docs",
                "product_hunt",
                "x",
                "other",
            ],
        )

    def test_target_platform_members(self) -> None:
        self.assertEqual(
            [p.value for p in TargetPlatform],
            [
                "telegram",
                "x",
                "linkedin",
                "reddit",
                "youtube_shorts",
                "tiktok",
                "pinterest",
            ],
        )

    def test_verification_status_members(self) -> None:
        self.assertEqual(
            [v.value for v in VerificationStatus],
            ["unverified", "verified", "disputed", "rejected"],
        )

    def test_package_variant_status_members(self) -> None:
        self.assertEqual(
            [v.value for v in PackageVariantStatus],
            ["planned", "drafted", "approved", "published", "skipped"],
        )

    def test_candidate_stage_members(self) -> None:
        self.assertEqual(
            [s.value for s in CandidateStage],
            [
                "discovered",
                "verified",
                "scored",
                "selected",
                "research_experiment",
                "content_cluster",
                "platform_adaptation",
                "published",
                "tracked",
                "learned",
            ],
        )


class TestExplicitClassification(unittest.TestCase):
    def test_candidate_requires_source_type(self) -> None:
        with self.assertRaises(TypeError):
            DiscoveryCandidate(
                candidate_id="c1",
                title="t",
                source_url="https://a.b",
                discovered_at="2026-09-08T10:00:00Z",
                content_cluster=ContentCluster.AI_TOOLS,
            )

    def test_candidate_requires_content_cluster(self) -> None:
        with self.assertRaises(TypeError):
            DiscoveryCandidate(
                candidate_id="c1",
                title="t",
                source_type=SourceType.GITHUB,
                source_url="https://a.b",
                discovered_at="2026-09-08T10:00:00Z",
            )

    def test_invalid_enum_strings_rejected_in_from_dict(self) -> None:
        payload = make_candidate().to_dict()

        bad_cluster = dict(payload, content_cluster="podcasts")
        with self.assertRaises(ValueError):
            DiscoveryCandidate.from_dict(bad_cluster)

        bad_source = dict(payload, source_type="tiktok_news")
        with self.assertRaises(ValueError):
            DiscoveryCandidate.from_dict(bad_source)

    def test_no_silent_fallback_to_ai_news(self) -> None:
        # A classification failure must raise, never fall back to ai_news
        # (or any other default cluster).
        payload = make_candidate().to_dict()
        del payload["content_cluster"]
        with self.assertRaises(ValueError):
            DiscoveryCandidate.from_dict(payload)

    def test_valid_enum_strings_accepted(self) -> None:
        candidate = DiscoveryCandidate.from_dict(make_candidate().to_dict())
        self.assertEqual(candidate.source_type, SourceType.GITHUB)
        self.assertEqual(candidate.content_cluster, ContentCluster.VIBE_CODING)
        # StrEnum stays str-comparable.
        self.assertEqual(candidate.content_cluster, "vibe_coding")


class TestCandidateScore(unittest.TestCase):
    def test_components_within_range_accepted(self) -> None:
        score = make_score(novelty=0.0, viral_potential=10.0)
        self.assertEqual(score.novelty, 0.0)
        self.assertEqual(score.viral_potential, 10.0)

    def test_total_score_is_deterministic(self) -> None:
        s1 = make_score()
        s2 = make_score()
        self.assertEqual(s1.total_score, s2.total_score)

    def test_total_score_uses_default_weights(self) -> None:
        score = make_score()
        expected = round(
            sum(
                getattr(score, component) * DEFAULT_SCORING_WEIGHTS[component]
                for component in SCORE_COMPONENTS
            ),
            4,
        )
        self.assertEqual(score.total_score, expected)

    def test_weight_sum_invariant(self) -> None:
        self.assertAlmostEqual(sum(DEFAULT_SCORING_WEIGHTS.values()), 1.0, places=9)
        self.assertEqual(set(DEFAULT_SCORING_WEIGHTS), set(SCORE_COMPONENTS))

    def test_out_of_range_components_fail_validation(self) -> None:
        result = validate_score(make_score(novelty=11.0, credibility=-0.5))
        self.assertFalse(result["valid"])
        joined = " ".join(result["issues"])
        self.assertIn("novelty", joined)
        self.assertIn("credibility", joined)

    def test_from_dict_ignores_supplied_total_score(self) -> None:
        score = make_score()
        payload = score.to_dict()
        payload["total_score"] = 99.99  # tampered stored value

        restored = CandidateScore.from_dict(payload)

        # The supplied total is ignored; the total is recomputed from components.
        self.assertEqual(restored.total_score, score.total_score)
        self.assertNotEqual(restored.total_score, 99.99)


class TestSerializationRoundTrips(unittest.TestCase):
    def test_discovery_candidate_round_trip(self) -> None:
        candidate = make_candidate(
            source_name="GitHub Trending",
            published_at="2026-09-07T18:00:00Z",
            summary="A new tool",
            raw_score=512,
            metadata={"stars": 1200, "language": "python"},
        )
        restored = DiscoveryCandidate.from_dict(candidate.to_dict())
        self.assertEqual(restored, candidate)

    def test_verification_result_round_trip(self) -> None:
        verification = VerificationResult(
            verification_status=VerificationStatus.VERIFIED,
            primary_source_found=True,
            primary_source_url="https://example.com/announcement",
            confidence=0.92,
            notes="Official blog post found",
        )
        restored = VerificationResult.from_dict(verification.to_dict())
        self.assertEqual(restored, verification)

    def test_candidate_score_round_trip(self) -> None:
        score = make_score()
        restored = CandidateScore.from_dict(score.to_dict())
        self.assertEqual(restored, score)

    def test_strategic_selection_round_trip(self) -> None:
        selection = StrategicSelection(
            selected=True,
            selection_reason="Highest practical utility this cycle",
            recommended_format=ContentFormat.TOOL_DISCOVERY,
            target_platforms=(TargetPlatform.TELEGRAM, TargetPlatform.X),
            research_required=True,
            experiment_required=False,
        )
        restored = StrategicSelection.from_dict(selection.to_dict())
        self.assertEqual(restored, selection)

    def test_content_candidate_round_trip(self) -> None:
        aggregate = ContentCandidate(
            candidate=make_candidate(),
            verification=VerificationResult(confidence=0.8),
            score=make_score(),
            selection=StrategicSelection(selected=False),
            stage=CandidateStage.SCORED,
            content_id=None,
        )
        restored = ContentCandidate.from_dict(aggregate.to_dict())
        self.assertEqual(restored, aggregate)

    def test_platform_variant_round_trip(self) -> None:
        variant = PlatformVariant(
            platform=TargetPlatform.TELEGRAM,
            status=PackageVariantStatus.DRAFTED,
            scheduled_at="2026-09-09T07:00:00Z",
            published_at=None,
            external_post_id=None,
            post_url=None,
        )
        restored = PlatformVariant.from_dict(variant.to_dict())
        self.assertEqual(restored, variant)

    def test_content_package_round_trip(self) -> None:
        package = ContentPackage(
            package_id="pkg-1",
            candidate_id="cand-1",
            variants=(
                PlatformVariant(platform=TargetPlatform.TELEGRAM),
                PlatformVariant(platform=TargetPlatform.X),
            ),
            content_id="04e9bc1a-fbc4-5880-8970-e5e80cbf4df3",
            created_at="2026-09-08T12:00:00Z",
        )
        restored = ContentPackage.from_dict(package.to_dict())
        self.assertEqual(restored, package)


class TestVerificationValidation(unittest.TestCase):
    def test_verified_requires_primary_source_found(self) -> None:
        result = validate_verification(
            VerificationResult(
                verification_status=VerificationStatus.VERIFIED,
                primary_source_found=False,
                primary_source_url="https://example.com/src",
                confidence=0.9,
            )
        )
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("primary_source_found" in i for i in result["issues"])
        )

    def test_verified_requires_primary_source_url(self) -> None:
        result = validate_verification(
            VerificationResult(
                verification_status=VerificationStatus.VERIFIED,
                primary_source_found=True,
                primary_source_url=None,
                confidence=0.9,
            )
        )
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("primary_source_url" in i for i in result["issues"])
        )

    def test_confidence_bounds_enforced(self) -> None:
        for bad in (-0.1, 1.1):
            with self.subTest(confidence=bad):
                result = validate_verification(VerificationResult(confidence=bad))
                self.assertFalse(result["valid"])

    def test_unverified_allowed_without_primary_source(self) -> None:
        result = validate_verification(VerificationResult())
        self.assertTrue(result["valid"], result["issues"])

    def test_candidate_validation_rejects_bad_url_and_empty_title(self) -> None:
        bad_url = validate_candidate(make_candidate(source_url="not-a-url"))
        self.assertFalse(bad_url["valid"])

        empty_title = validate_candidate(make_candidate(title="   "))
        self.assertFalse(empty_title["valid"])

        good = validate_candidate(make_candidate())
        self.assertTrue(good["valid"], good["issues"])


class TestSelectionValidation(unittest.TestCase):
    def test_selected_requires_reason(self) -> None:
        result = validate_selection(
            StrategicSelection(selected=True, target_platforms=(TargetPlatform.X,))
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("selection_reason" in i for i in result["issues"]))

    def test_selected_requires_target_platform(self) -> None:
        result = validate_selection(
            StrategicSelection(selected=True, selection_reason="because")
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("platform" in i for i in result["issues"]))

    def test_invalid_target_platforms_rejected(self) -> None:
        # Construction-time type flexibility is allowed by the dataclass,
        # but validation must reject non-TargetPlatform members.
        bogus = StrategicSelection(
            selected=True,
            selection_reason="because",
            target_platforms=("myspace",),  # type: ignore[list-item]
        )
        result = validate_selection(bogus)
        self.assertFalse(result["valid"])
        self.assertTrue(any("myspace" in i for i in result["issues"]))

    def test_not_selected_may_have_no_platforms_or_reason(self) -> None:
        result = validate_selection(StrategicSelection(selected=False))
        self.assertTrue(result["valid"], result["issues"])

    def test_min_confidence_constant_sane(self) -> None:
        self.assertGreaterEqual(MIN_CONFIDENCE_FOR_SELECTION, 0.0)
        self.assertLessEqual(MIN_CONFIDENCE_FOR_SELECTION, 1.0)


class TestEditorialInvariants(unittest.TestCase):
    def test_ai_news_is_last_in_cluster_priority(self) -> None:
        self.assertEqual(CLUSTER_PRIORITY[-1], ContentCluster.AI_NEWS)
        self.assertNotIn(ContentCluster.AI_NEWS, CLUSTER_PRIORITY[:-1])

    def test_cluster_priority_is_data_only(self) -> None:
        # It is an immutable data tuple — future selection algorithms will
        # combine it with scoring; nothing here may behave like a selector.
        self.assertIsInstance(CLUSTER_PRIORITY, tuple)
        self.assertEqual(len(CLUSTER_PRIORITY), len(ContentCluster))

    def test_high_quality_ai_news_not_structurally_forbidden(self) -> None:
        # ai_news must remain a valid, constructible, selectable cluster —
        # demotion is data-driven priority, not a structural ban.
        candidate = make_candidate(
            title="Major lab releases breakthrough model",
            content_cluster=ContentCluster.AI_NEWS,
            source_type=SourceType.HACKER_NEWS,
            source_url="https://news.ycombinator.com/item?id=1",
        )
        self.assertTrue(validate_candidate(candidate)["valid"])
        self.assertIn(ContentCluster.AI_NEWS, CLUSTER_PRIORITY)


class TestFrozenDataclasses(unittest.TestCase):
    def test_mutation_raises_for_representative_models(self) -> None:
        candidate = make_candidate()
        with self.assertRaises(FrozenInstanceError):
            candidate.title = "mutated"

        score = make_score()
        with self.assertRaises(FrozenInstanceError):
            score.novelty = 0.0

        selection = StrategicSelection(selected=False)
        with self.assertRaises(FrozenInstanceError):
            selection.selected = True

        package = ContentPackage(package_id="p", candidate_id="c")
        with self.assertRaises(FrozenInstanceError):
            package.package_id = "x"


class TestContentPackage(unittest.TestCase):
    def test_can_represent_all_seven_target_platforms(self) -> None:
        variants = tuple(
            PlatformVariant(platform=platform) for platform in TargetPlatform
        )
        self.assertEqual(len(variants), 7)
        package = ContentPackage(
            package_id="pkg-all",
            candidate_id="cand-1",
            variants=variants,
        )
        covered = {variant.platform for variant in package.variants}
        self.assertEqual(covered, set(TargetPlatform))
        restored = ContentPackage.from_dict(package.to_dict())
        self.assertEqual({v.platform for v in restored.variants}, covered)

    def test_variants_remain_platform_native_records(self) -> None:
        # Each variant is an independent per-platform record (own status,
        # schedule, external IDs) — not one shared text blob on the package.
        package = ContentPackage(
            package_id="pkg-native",
            candidate_id="cand-1",
            variants=(
                PlatformVariant(
                    platform=TargetPlatform.TELEGRAM,
                    status=PackageVariantStatus.PUBLISHED,
                    external_post_id="307",
                    post_url="https://t.me/nejroavtomatizacia/307",
                ),
                PlatformVariant(
                    platform=TargetPlatform.X,
                    status=PackageVariantStatus.DRAFTED,
                ),
            ),
        )
        telegram = next(v for v in package.variants if v.platform is TargetPlatform.TELEGRAM)
        twitter = next(v for v in package.variants if v.platform is TargetPlatform.X)
        self.assertEqual(telegram.status, PackageVariantStatus.PUBLISHED)
        self.assertEqual(telegram.external_post_id, "307")
        self.assertEqual(twitter.status, PackageVariantStatus.DRAFTED)
        self.assertIsNone(twitter.external_post_id)


class TestSoftLinkBehavior(unittest.TestCase):
    def test_content_id_may_be_none(self) -> None:
        aggregate = ContentCandidate(candidate=make_candidate())
        self.assertIsNone(aggregate.content_id)

    def test_content_id_accepts_string_without_db_dependency(self) -> None:
        aggregate = ContentCandidate(
            candidate=make_candidate(),
            content_id="04e9bc1a-fbc4-5880-8970-e5e80cbf4df3",
        )
        self.assertEqual(aggregate.content_id, "04e9bc1a-fbc4-5880-8970-e5e80cbf4df3")
        restored = ContentCandidate.from_dict(aggregate.to_dict())
        self.assertEqual(restored.content_id, aggregate.content_id)
        # Round-trip carries the soft link with no database involvement.
        self.assertIsInstance(restored.content_id, str)


if __name__ == "__main__":
    unittest.main()
