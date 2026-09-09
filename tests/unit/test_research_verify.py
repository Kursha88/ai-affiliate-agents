"""Unit tests for Stage 3.2 deterministic provenance verification.

Covers the approved decision table (GitHub repository provenance,
trusted official domains, HN-native posts, HN discussion URLs, generic
secondary sources, missing/malformed URLs, GitHub identity conflicts),
determinism, VerificationResult consistency (including
``validate_verification`` compatibility), provenance-vs-fact-checking
boundaries (metadata mentioning GitHub never verifies), no mutation of
``RawDiscovery``, and structural guarantees (no network/DB imports, no
classification/scoring/ranking, URL logic reused from
``src.research.normalize``).

All inputs are in-memory ``RawDiscovery`` records; no network access.
"""

from __future__ import annotations

import ast
import copy
import inspect
import unittest

from src.domain.strategy import (
    SourceType,
    VerificationStatus,
    validate_verification,
)
from src.research.adapters.base import RawDiscovery
from src.research.verify import (
    CONFIDENCE_GITHUB_REPOSITORY,
    CONFIDENCE_HN_NATIVE,
    CONFIDENCE_OFFICIAL_TRUSTED_DOMAIN,
    CONFIDENCE_REJECTED,
    CONFIDENCE_SECONDARY,
    NOTE_DISPUTED_GITHUB_IDENTITY_CONFLICT,
    NOTE_PRIMARY_GITHUB_REPOSITORY,
    NOTE_PRIMARY_HN_NATIVE,
    NOTE_PRIMARY_TRUSTED_OFFICIAL_DOMAIN,
    NOTE_REJECTED_MALFORMED_URL,
    NOTE_REJECTED_MISSING_URL,
    NOTE_SECONDARY_HACKER_NEWS_DISCUSSION,
    NOTE_SECONDARY_UNTRUSTED_DOMAIN,
    verify_provenance,
)


def make_discovery(
    title: str = "Some AI tool announcement",
    url: str | None = "https://example.com/article",
    source_name: str = "hacker_news",
    identifiers: dict | None = None,
    metadata: dict | None = None,
    summary: str = "",
) -> RawDiscovery:
    return RawDiscovery(
        title=title,
        url=url,
        source_name=source_name,
        discovered_at="2026-09-08T12:00:00Z",
        summary=summary,
        identifiers=identifiers if identifiers is not None else {},
        metadata=metadata if metadata is not None else {},
    )


def verify(
    discovery: RawDiscovery,
    source_type: SourceType = SourceType.HACKER_NEWS,
    trusted=("openai.com",),
):
    return verify_provenance(
        discovery,
        source_type,
        trusted_primary_domains=trusted,
    )


# ══════════════════════════════════════════════════════════════════════
# 1. GitHub repository provenance
# ══════════════════════════════════════════════════════════════════════


class TestGitHubRepositoryProvenance(unittest.TestCase):
    def test_repo_root_url_verified(self):
        result = verify(
            make_discovery(url="https://github.com/org/tool"),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.confidence, CONFIDENCE_GITHUB_REPOSITORY)
        self.assertEqual(result.notes, NOTE_PRIMARY_GITHUB_REPOSITORY)
        self.assertTrue(result.primary_source_found)
        self.assertEqual(result.primary_source_url, "https://github.com/org/tool")

    def test_repo_root_url_trailing_slash_verified(self):
        result = verify(
            make_discovery(url="https://github.com/org/tool/"),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.primary_source_url, "https://github.com/org/tool")

    def test_repo_root_url_verified_for_any_source_type(self):
        # The URL itself IS the repository resource; source type is
        # irrelevant for rule 5a.
        for source_type in (SourceType.HACKER_NEWS, SourceType.OTHER, SourceType.GITHUB):
            result = verify(make_discovery(url="https://github.com/org/tool"), source_type)
            self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
            self.assertEqual(result.notes, NOTE_PRIMARY_GITHUB_REPOSITORY)

    def test_identifier_plus_matching_repo_root_url_verified(self):
        result = verify(
            make_discovery(
                url="https://github.com/org/tool",
                identifiers={"github_repo": "org/tool"},
            ),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.notes, NOTE_PRIMARY_GITHUB_REPOSITORY)

    def test_identifier_plus_matching_deep_link_verified(self):
        # Deep link + declared identity: the declaration justifies
        # canonicalizing to the repo root.
        result = verify(
            make_discovery(
                url="https://github.com/org/tool/releases/tag/v1.2.0",
                identifiers={"github_repo": "org/tool"},
            ),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.confidence, CONFIDENCE_GITHUB_REPOSITORY)
        self.assertEqual(result.primary_source_url, "https://github.com/org/tool")

    def test_identifier_plus_deep_link_verified_for_non_github_source(self):
        # Rule 5b is source-neutral: declaration + corroborating github.com
        # URL verifies regardless of adapter.
        result = verify(
            make_discovery(
                url="https://github.com/org/tool/blob/main/README.md",
                identifiers={"github_repo": "org/tool"},
            ),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.primary_source_url, "https://github.com/org/tool")

    def test_www_github_and_case_normalization(self):
        result = verify(
            make_discovery(url="https://www.github.com/Org/Tool/"),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.primary_source_url, "https://github.com/org/tool")

    def test_metadata_mentioning_github_never_verifies(self):
        # CRITICAL: random metadata referencing a GitHub repo must not
        # trigger repository provenance.
        result = verify(
            make_discovery(
                url="https://techcrunch.com/some-tool-launch",
                metadata={"project": "github.com/org/tool", "repo": "org/tool"},
            ),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertNotEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
        self.assertFalse(result.primary_source_found)

    def test_identifier_without_corroborating_url_not_verified(self):
        # A declared identifier alone (URL points elsewhere) is not repo
        # provenance for a non-GITHUB source.
        result = verify(
            make_discovery(
                url="https://example.com/article",
                identifiers={"github_repo": "org/tool"},
            ),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)

    def test_deep_github_url_without_declaration_not_repo_provenance(self):
        # An issue/blob page is not the repository resource.
        result = verify(
            make_discovery(url="https://github.com/org/tool/issues/123"),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
        self.assertNotEqual(result.notes, NOTE_PRIMARY_GITHUB_REPOSITORY)


# ══════════════════════════════════════════════════════════════════════
# 2. GitHub identity conflicts (DISPUTED)
# ══════════════════════════════════════════════════════════════════════


class TestGitHubIdentityConflict(unittest.TestCase):
    def test_declared_repo_but_non_github_url_disputed(self):
        result = verify(
            make_discovery(
                url="https://example.com/landing-page",
                identifiers={"github_repo": "org/tool"},
            ),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.verification_status, VerificationStatus.DISPUTED)
        self.assertEqual(result.confidence, CONFIDENCE_REJECTED)
        self.assertEqual(result.notes, NOTE_DISPUTED_GITHUB_IDENTITY_CONFLICT)
        self.assertFalse(result.primary_source_found)

    def test_declared_repo_but_different_github_repo_disputed(self):
        result = verify(
            make_discovery(
                url="https://github.com/other/project",
                identifiers={"github_repo": "org/tool"},
            ),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.verification_status, VerificationStatus.DISPUTED)
        self.assertEqual(result.notes, NOTE_DISPUTED_GITHUB_IDENTITY_CONFLICT)

    def test_conflict_only_for_github_source_type(self):
        # The same contradiction on a non-GITHUB source is NOT disputed:
        # rule 3 is gated to the adapter owning the namespace; the
        # identifier is simply not corroborated (UNVERIFIED).
        result = verify(
            make_discovery(
                url="https://example.com/landing-page",
                identifiers={"github_repo": "org/tool"},
            ),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)

    def test_malformed_identifier_never_disputes(self):
        # A malformed identifier is merely ignored (conservative): there
        # is no declared identity, so no contradiction can exist. The
        # URL stays usable -> UNVERIFIED, never DISPUTED.
        for bad in ("", "   ", "justowner", "/leading", "trailing/", 123, None):
            result = verify(
                make_discovery(
                    url="https://example.com/landing",
                    identifiers={"github_repo": bad},
                ),
                source_type=SourceType.GITHUB,
            )
            self.assertEqual(
                result.verification_status, VerificationStatus.UNVERIFIED
            )
            self.assertNotEqual(
                result.notes, NOTE_DISPUTED_GITHUB_IDENTITY_CONFLICT
            )


# ══════════════════════════════════════════════════════════════════════
# 3. Trusted official domains
# ══════════════════════════════════════════════════════════════════════


class TestTrustedOfficialDomains(unittest.TestCase):
    def test_official_blog_on_trusted_domain_verified(self):
        result = verify(
            make_discovery(
                url="https://openai.com/index/introducing-gpt-6",
                source_name="official_blog",
            ),
            source_type=SourceType.OFFICIAL_BLOG,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.confidence, CONFIDENCE_OFFICIAL_TRUSTED_DOMAIN)
        self.assertEqual(result.notes, NOTE_PRIMARY_TRUSTED_OFFICIAL_DOMAIN)
        self.assertTrue(result.primary_source_found)
        self.assertEqual(result.primary_source_url, "https://openai.com/index/introducing-gpt-6")

    def test_official_docs_on_trusted_domain_verified(self):
        result = verify(
            make_discovery(
                url="https://platform.openai.com/docs/guides/agents",
                source_name="official_docs",
            ),
            source_type=SourceType.OFFICIAL_DOCS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.notes, NOTE_PRIMARY_TRUSTED_OFFICIAL_DOMAIN)

    def test_trusted_subdomain_accepted(self):
        result = verify(make_discovery(url="https://research.openai.com/post"))
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)

    def test_www_trusted_host_accepted(self):
        result = verify(make_discovery(url="https://www.openai.com/post"))
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)

    def test_lookalike_domains_rejected_from_trust(self):
        # Neither lookalike may verify as trusted; both are secondary.
        for url in (
            "https://fakeopenai.com/announcement",
            "https://openai.com.evil.example/announcement",
        ):
            result = verify(make_discovery(url=url))
            self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
            self.assertFalse(result.primary_source_found)
            self.assertEqual(result.notes, NOTE_SECONDARY_UNTRUSTED_DOMAIN)

    def test_official_source_type_alone_never_verifies(self):
        # SourceType alone is NOT evidence: empty trusted set must never
        # produce VERIFIED, whatever the source type.
        for source_type in (
            SourceType.OFFICIAL_BLOG,
            SourceType.OFFICIAL_DOCS,
            SourceType.GITHUB,
        ):
            result = verify(
                make_discovery(url="https://unknown-vendor.example/blog"),
                source_type,
                trusted=(),
            )
            self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
            self.assertFalse(result.primary_source_found)

    def test_trust_is_source_type_agnostic(self):
        # HN outbound to a trusted official domain verifies the primary
        # source even though the adapter is HN.
        result = verify(
            make_discovery(url="https://openai.com/announcement"),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.confidence, CONFIDENCE_OFFICIAL_TRUSTED_DOMAIN)

    def test_hn_outbound_to_unknown_domain_unverified(self):
        result = verify(
            make_discovery(url="https://techcrunch.com/story"),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
        self.assertEqual(result.confidence, CONFIDENCE_SECONDARY)
        self.assertEqual(result.notes, NOTE_SECONDARY_UNTRUSTED_DOMAIN)

    def test_malformed_trusted_entries_ignored(self):
        # Fail-closed: junk entries never match anything.
        result = verify(
            make_discovery(url="https://openai.com/post"),
            trusted=("openai.com", "not a domain", "", "...", "openai com"),
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)

    def test_non_string_trusted_entries_ignored(self):
        result = verify(
            make_discovery(url="https://openai.com/post"),
            trusted=("openai.com", 42, None, ["openai.com"]),  # type: ignore[list-item]
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)


# ══════════════════════════════════════════════════════════════════════
# 4. Hacker News provenance
# ══════════════════════════════════════════════════════════════════════


class TestHackerNewsProvenance(unittest.TestCase):
    def test_hn_native_post_verified_with_lower_confidence(self):
        result = verify(
            make_discovery(
                url="https://news.ycombinator.com/item?id=424242",
                metadata={
                    "hn_native": True,
                    "hn_item_url": "https://news.ycombinator.com/item?id=424242",
                },
            ),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.confidence, CONFIDENCE_HN_NATIVE)
        self.assertLess(result.confidence, CONFIDENCE_OFFICIAL_TRUSTED_DOMAIN)
        self.assertGreater(result.confidence, CONFIDENCE_SECONDARY)
        self.assertEqual(result.notes, NOTE_PRIMARY_HN_NATIVE)
        self.assertTrue(result.primary_source_found)
        self.assertEqual(result.primary_source_url, "https://news.ycombinator.com/item?id=424242")

    def test_hn_native_flag_but_outbound_url_is_not_native(self):
        # hn_native=True with a record URL pointing elsewhere: the URL
        # must match the native item URL, otherwise HN is not primary.
        result = verify(
            make_discovery(
                url="https://example.com/outbound",
                metadata={
                    "hn_native": True,
                    "hn_item_url": "https://news.ycombinator.com/item?id=424242",
                },
            ),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
        self.assertNotEqual(result.notes, NOTE_PRIMARY_HN_NATIVE)

    def test_hn_native_string_true_not_honored(self):
        # Strict boolean contract: "true" (string) does not qualify.
        result = verify(
            make_discovery(
                url="https://news.ycombinator.com/item?id=424242",
                metadata={
                    "hn_native": "true",
                    "hn_item_url": "https://news.ycombinator.com/item?id=424242",
                },
            ),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
        self.assertEqual(result.notes, NOTE_SECONDARY_HACKER_NEWS_DISCUSSION)

    def test_hn_native_url_variants_match_via_normalizer(self):
        # www./tracking-param variants of the native item URL still match.
        result = verify(
            make_discovery(
                url="https://news.ycombinator.com/item?id=424242&utm_source=rss",
                metadata={
                    "hn_native": True,
                    "hn_item_url": "https://news.ycombinator.com/item?id=424242",
                },
            ),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(result.notes, NOTE_PRIMARY_HN_NATIVE)

    def test_hn_discussion_url_without_native_flag_is_secondary(self):
        result = verify(
            make_discovery(
                url="https://news.ycombinator.com/item?id=111111",
                metadata={"hn_item_url": "https://news.ycombinator.com/item?id=111111"},
            ),
            source_type=SourceType.HACKER_NEWS,
        )
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
        self.assertEqual(result.notes, NOTE_SECONDARY_HACKER_NEWS_DISCUSSION)


# ══════════════════════════════════════════════════════════════════════
# 5. Generic secondary sources
# ══════════════════════════════════════════════════════════════════════


class TestGenericSecondarySources(unittest.TestCase):
    def test_unknown_secondary_article_unverified_not_rejected(self):
        result = verify(
            make_discovery(
                url="https://some-independent-blog.io/ai-agents-2026",
                source_name="blog_rss",
            ),
            source_type=SourceType.OTHER,
        )
        self.assertEqual(result.verification_status, VerificationStatus.UNVERIFIED)
        self.assertFalse(result.primary_source_found)
        self.assertIsNone(result.primary_source_url)
        self.assertEqual(result.confidence, CONFIDENCE_SECONDARY)
        self.assertEqual(result.notes, NOTE_SECONDARY_UNTRUSTED_DOMAIN)

    def test_secondary_confidence_below_selection_threshold(self):
        # Provenance alone must never make a secondary source selectable.
        self.assertLess(CONFIDENCE_SECONDARY, 0.7)


# ══════════════════════════════════════════════════════════════════════
# 6. Missing / malformed URLs
# ══════════════════════════════════════════════════════════════════════


class TestMissingAndMalformedUrls(unittest.TestCase):
    def test_missing_url_rejected(self):
        result = verify(make_discovery(url=None))
        self.assertEqual(result.verification_status, VerificationStatus.REJECTED)
        self.assertEqual(result.confidence, CONFIDENCE_REJECTED)
        self.assertEqual(result.notes, NOTE_REJECTED_MISSING_URL)
        self.assertFalse(result.primary_source_found)
        self.assertIsNone(result.primary_source_url)

    def test_blank_url_rejected(self):
        for blank in ("", "   "):
            result = verify(make_discovery(url=blank))
            self.assertEqual(result.verification_status, VerificationStatus.REJECTED)
            self.assertEqual(result.notes, NOTE_REJECTED_MISSING_URL)

    def test_malformed_url_rejected(self):
        for url in ("not a url at all", "example.com/no-scheme", "//example.com/x"):
            result = verify(make_discovery(url=url))
            self.assertEqual(result.verification_status, VerificationStatus.REJECTED)
            self.assertEqual(result.notes, NOTE_REJECTED_MALFORMED_URL)

    def test_unsupported_scheme_rejected(self):
        for url in ("ftp://example.com/file", "javascript:alert(1)"):
            result = verify(make_discovery(url=url))
            self.assertEqual(result.verification_status, VerificationStatus.REJECTED)
            self.assertEqual(result.notes, NOTE_REJECTED_MALFORMED_URL)

    def test_dotless_host_rejected(self):
        result = verify(make_discovery(url="https://localhost/tool"))
        self.assertEqual(result.verification_status, VerificationStatus.REJECTED)
        self.assertEqual(result.notes, NOTE_REJECTED_MALFORMED_URL)

    def test_rejection_even_with_strong_metadata(self):
        # A broken identity cannot be rescued by metadata or identifiers.
        result = verify(
            make_discovery(
                url="ftp://example.com/file",
                identifiers={"github_repo": "org/tool"},
                metadata={"hn_native": True},
            ),
            source_type=SourceType.GITHUB,
        )
        self.assertEqual(result.verification_status, VerificationStatus.REJECTED)


# ══════════════════════════════════════════════════════════════════════
# 7. Determinism and VerificationResult consistency
# ══════════════════════════════════════════════════════════════════════


class TestDeterminismAndContract(unittest.TestCase):
    def test_deterministic_repeated_calls(self):
        discovery = make_discovery(url="https://openai.com/post")
        self.assertEqual(
            verify(discovery),
            verify(discovery),
        )

    def test_result_contract_shape(self):
        result = verify(make_discovery(url="https://openai.com/post"))
        self.assertEqual(
            set(result.__dataclass_fields__),
            {
                "verification_status",
                "primary_source_found",
                "primary_source_url",
                "confidence",
                "notes",
            },
        )

    def test_every_status_result_passes_validate_verification(self):
        cases = [
            make_discovery(url="https://github.com/org/tool"),          # VERIFIED
            make_discovery(url="https://openai.com/post"),               # VERIFIED
            make_discovery(                                              # VERIFIED (native)
                url="https://news.ycombinator.com/item?id=1",
                metadata={"hn_native": True,
                          "hn_item_url": "https://news.ycombinator.com/item?id=1"},
            ),
            make_discovery(url="https://techcrunch.com/x"),              # UNVERIFIED
            make_discovery(url="https://news.ycombinator.com/item?id=2"),  # UNVERIFIED
            make_discovery(url=None),                                     # REJECTED
            make_discovery(url="ftp://example.com/f"),                    # REJECTED
            make_discovery(                                               # DISPUTED
                url="https://example.com/x",
                identifiers={"github_repo": "org/tool"},
            ),
        ]
        for source_type, case in zip(
            (
                SourceType.GITHUB, SourceType.OFFICIAL_BLOG, SourceType.HACKER_NEWS,
                SourceType.HACKER_NEWS, SourceType.HACKER_NEWS,
                SourceType.HACKER_NEWS, SourceType.GITHUB, SourceType.GITHUB,
            ),
            cases,
        ):
            with self.subTest(source_type=source_type):
                result = verify(case, source_type)
                self.assertEqual(validate_verification(result), {"valid": True, "issues": []})
                self.assertIsInstance(result.verification_status, VerificationStatus)
                self.assertTrue(0.0 <= result.confidence <= 1.0)
                if result.verification_status == VerificationStatus.VERIFIED:
                    self.assertTrue(result.primary_source_found)
                    self.assertTrue(result.primary_source_url)
                else:
                    self.assertFalse(result.primary_source_found)
                    self.assertIsNone(result.primary_source_url)

    def test_notes_vocabulary_is_closed(self):
        from src.research import verify as verify_module

        allowed = {
            NOTE_PRIMARY_GITHUB_REPOSITORY,
            NOTE_PRIMARY_TRUSTED_OFFICIAL_DOMAIN,
            NOTE_PRIMARY_HN_NATIVE,
            NOTE_SECONDARY_UNTRUSTED_DOMAIN,
            NOTE_SECONDARY_HACKER_NEWS_DISCUSSION,
            NOTE_REJECTED_MISSING_URL,
            NOTE_REJECTED_MALFORMED_URL,
            NOTE_DISPUTED_GITHUB_IDENTITY_CONFLICT,
        }
        inputs = [
            (make_discovery(url="https://github.com/o/r"), SourceType.GITHUB),
            (make_discovery(url="https://openai.com/p"), SourceType.OFFICIAL_BLOG),
            (make_discovery(url="https://n.ycombinator.com/item?id=1",
                            metadata={"hn_native": True,
                                      "hn_item_url": "https://n.ycombinator.com/item?id=1"}),
             SourceType.HACKER_NEWS),
            (make_discovery(url="https://news.ycombinator.com/item?id=2"), SourceType.HACKER_NEWS),
            (make_discovery(url="https://tcrunch.com/a"), SourceType.HACKER_NEWS),
            (make_discovery(url=None), SourceType.HACKER_NEWS),
            (make_discovery(url="nope"), SourceType.HACKER_NEWS),
            (make_discovery(url="https://x.com/a", identifiers={"github_repo": "o/r"}),
             SourceType.GITHUB),
        ]
        for discovery, source_type in inputs:
            result = verify_provenance(discovery, source_type, trusted_primary_domains=("openai.com",))
            self.assertIn(result.notes, allowed)

    def test_confidence_constants_hierarchy(self):
        self.assertGreater(
            CONFIDENCE_OFFICIAL_TRUSTED_DOMAIN, CONFIDENCE_GITHUB_REPOSITORY
        )
        self.assertGreater(CONFIDENCE_GITHUB_REPOSITORY, CONFIDENCE_HN_NATIVE)
        self.assertGreater(CONFIDENCE_HN_NATIVE, CONFIDENCE_SECONDARY)
        self.assertGreater(CONFIDENCE_SECONDARY, CONFIDENCE_REJECTED)


# ══════════════════════════════════════════════════════════════════════
# 8. Purity: no mutation, no fact-checking leakage
# ══════════════════════════════════════════════════════════════════════


class TestPurity(unittest.TestCase):
    def test_raw_discovery_not_mutated(self):
        discovery = make_discovery(
            url="https://github.com/Org/Tool/?utm_source=x",
            identifiers={"github_repo": "org/tool"},
            metadata={"hn_native": False, "nested": {"a": [1, 2]}},
        )
        snapshot = copy.deepcopy(discovery)
        verify_provenance(
            discovery, SourceType.GITHUB, trusted_primary_domains=("openai.com",)
        )
        self.assertEqual(discovery, snapshot)

    def test_verified_is_not_claim_fact_checking(self):
        # VERIFIED provenance must not be tied to any claim content in
        # title/summary — a trusted-domain URL with absurd claims is
        # still verified provenance, an untrusted one stays unverified
        # regardless of how plausible its text sounds.
        strong_claim = "cures all diseases 100% free benchmark beats everything"
        trusted = verify(
            make_discovery(url="https://openai.com/post", title=strong_claim, summary=strong_claim)
        )
        untrusted = verify(
            make_discovery(url="https://random-blog.xyz/post", title=strong_claim, summary=strong_claim)
        )
        self.assertEqual(trusted.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(untrusted.verification_status, VerificationStatus.UNVERIFIED)


# ══════════════════════════════════════════════════════════════════════
# 9. Structural guarantees (AST-level, mirroring test_research_dedup.py)
# ══════════════════════════════════════════════════════════════════════


class TestStructuralGuarantees(unittest.TestCase):
    """AST-level guarantees about the verify module's CODE.

    Docstrings are stripped before text scans: the module legitimately
    *documents* forbidden concepts ("no CLUSTER_PRIORITY", "no
    CandidateScore"); the guarantee is that the code never uses them.
    """

    @classmethod
    def _module_source(cls) -> str:
        from src.research import verify as verify_module

        return inspect.getsource(verify_module)

    @classmethod
    def _code_source(cls) -> str:
        """Module source with all docstrings removed (code only)."""
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

    def _module_imports(self, source: str) -> set:
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        return imported

    def _module_names(self, source: str) -> set:
        return {
            node.id
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Name)
        }

    def test_no_db_network_publishing_imports(self):
        imported = self._module_imports(self._module_source())
        forbidden = {
            "requests", "urllib.request", "socket", "http", "httpx",
            "sqlite3", "subprocess", "os", "pathlib",
            "src.main", "src.storage", "src.factory", "src.agents", "src.integrations",
        }
        self.assertFalse(imported & forbidden)

    def test_no_classification_scoring_ranking_imports(self):
        source = self._module_source()
        imported = self._module_imports(source)
        self.assertFalse(
            imported & {"src.research.classify", "src.research.score", "src.research.rank"}
        )
        names = self._module_names(self._code_source())
        self.assertNotIn("CandidateScore", names)
        self.assertNotIn("classify", names)

    def test_no_cluster_priority_dependency(self):
        # Docstrings are stripped: documenting the prohibition is fine,
        # depending on it is not.
        self.assertNotIn("CLUSTER_PRIORITY", self._code_source())

    def test_does_not_construct_discovery_candidate(self):
        self.assertNotIn(
            "DiscoveryCandidate", self._module_names(self._code_source())
        )

    def test_url_logic_reused_from_normalize(self):
        # Proves the module reuses src.research.normalize instead of
        # duplicating URL normalization logic.
        source = self._module_source()
        self.assertIn("src.research.normalize", self._module_imports(source))
        self.assertIn("normalize_url", self._module_names(source))

    def test_no_hardcoded_vendor_domain_list(self):
        # No large vendor list may hide in the module's code: the only
        # trusted domains come from the caller.
        source = self._code_source().lower()
        for vendor in ("openai", "anthropic", "google.com", "meta.com", "microsoft", "deepmind"):
            self.assertNotIn(vendor, source)


if __name__ == "__main__":
    unittest.main()
