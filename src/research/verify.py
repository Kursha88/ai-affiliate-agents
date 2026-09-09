"""Deterministic provenance/source verification (Stage 3.2).

CRITICAL SEMANTIC BOUNDARY: provenance verification is NOT claim
fact-checking. This module answers only:

- Is there a plausible primary/source-of-record resource?
- Is the discovery itself a primary source (e.g. a GitHub repository
  the record represents, or an HN-native post)?
- Is provenance explicit (a trusted official domain)?
- Is this only secondary/community coverage?
- How strong is the deterministic provenance evidence?

It must NEVER be read as claiming that arbitrary factual/comparative/
pricing/performance/feature/safety statements in a discovery are true.
A VERIFIED result means "the source identity is strong", nothing more.

Status semantics (``src.domain.strategy.VerificationStatus``):

- ``VERIFIED``:   strong deterministic provenance evidence (the
                  discovery clearly represents a primary source, points
                  at one, or carries an explicit trusted-domain host).
- ``UNVERIFIED``: usable discovery, no strong primary provenance
                  (secondary/community coverage). NOT a rejection.
- ``REJECTED``:   malformed/unusable provenance identity (missing URL,
                  non-http(s) scheme, unparseable or dotless host).
- ``DISPUTED``:   reserved for explicit contradictory provenance
                  evidence — here: a GitHub-adapter record whose
                  declared ``github_repo`` identity is contradicted by
                  its own URL. NEVER used merely for low confidence.

Design invariants:

1. Pure and deterministic: no network, no DNS resolution, no I/O, no
   clock, no randomness. Same input -> same result object.
2. ``RawDiscovery`` is read-only; it is never mutated.
3. URL normalization is delegated entirely to ``src.research.normalize``
   (no duplicated scheme/host logic). ``github_repo_identity()`` is
   repo-level identity only: deep GitHub links are canonicalized to a
   repo root ONLY when the record itself represents that repository
   (repo-root URL, or an adapter-declared ``identifiers["github_repo"]``
   corroborated by a github.com URL). Metadata merely mentioning GitHub
   is never inspected for provenance.
4. No vendor/domain list is hardcoded: trusted official domains are
   supplied per call by the orchestrator.
5. No persistence (no factory.db, no migrations, no topic_history).
6. No scoring/ranking: no ``CandidateScore``, no ``CLUSTER_PRIORITY``,
   no selection decisions. ``verify_provenance`` never constructs a
   ``DiscoveryCandidate``.
7. Every emitted result satisfies ``validate_verification``: VERIFIED
   implies ``primary_source_found=True`` with a usable
   ``primary_source_url``; all other statuses leave both empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urlsplit

from src.domain.strategy import SourceType, VerificationResult, VerificationStatus
from src.research.adapters.base import RawDiscovery
from src.research.normalize import github_repo_identity, normalize_url

# ──────────────────────────────────────────────────────────────────────
# Deterministic provenance-strength constants (NOT probabilities).
#
# The scale is deliberately small and centralized. Ordering matters:
# official trusted source > GitHub repository > HN-native post >
# secondary source > rejected. All secondary/rejected values sit far
# below MIN_CONFIDENCE_FOR_SELECTION (0.7, strategy.py) so provenance
# alone can never make a weakly-sourced candidate selectable.
# ──────────────────────────────────────────────────────────────────────

#: Host explicitly designated official by the orchestrator and matched
#: on exact hostname boundaries. Not 1.0: nothing deterministic is absolute.
CONFIDENCE_OFFICIAL_TRUSTED_DOMAIN: float = 0.95

#: Repository identity is explicit (repo-root URL, or declared
#: identifier corroborated by a github.com URL). Below the official
#: trusted domain because anyone can create ``owner/repo`` namespaces.
CONFIDENCE_GITHUB_REPOSITORY: float = 0.90

#: HN genuinely hosts the native post (primary for that post), but it
#: is a community platform, not an editorial/offical publisher.
CONFIDENCE_HN_NATIVE: float = 0.75

#: Usable discovery, no strong primary provenance (secondary article,
#: untrusted domain, HN discussion URL). Deliberately below 0.7.
CONFIDENCE_SECONDARY: float = 0.35

#: No provenance established (rejected or disputed identity).
CONFIDENCE_REJECTED: float = 0.0

# ──────────────────────────────────────────────────────────────────────
# Stable note/reason vocabulary (concise, observable, no secrets,
# no metadata dumps). Keep this set closed and small.
# ──────────────────────────────────────────────────────────────────────

NOTE_PRIMARY_GITHUB_REPOSITORY: str = "primary:github_repository"
NOTE_PRIMARY_TRUSTED_OFFICIAL_DOMAIN: str = "primary:trusted_official_domain"
NOTE_PRIMARY_HN_NATIVE: str = "primary:hn_native"
NOTE_SECONDARY_UNTRUSTED_DOMAIN: str = "secondary:untrusted_domain"
NOTE_SECONDARY_HACKER_NEWS_DISCUSSION: str = "secondary:hacker_news_discussion"
NOTE_REJECTED_MISSING_URL: str = "rejected:missing_url"
NOTE_REJECTED_MALFORMED_URL: str = "rejected:malformed_url"
NOTE_DISPUTED_GITHUB_IDENTITY_CONFLICT: str = "disputed:github_identity_conflict"


@dataclass(frozen=True)
class _TrustedDomains:
    """Normalized trusted-domain set (fail-closed on malformed entries)."""

    entries: frozenset[str]

    @classmethod
    def build(cls, trusted: Iterable[str]) -> "_TrustedDomains":
        cleaned: set[str] = set()
        for entry in trusted or ():
            if not isinstance(entry, str):
                continue
            host = entry.strip().lower()
            if host.startswith("www."):
                host = host[4:]
            # A trusted entry must look like a domain: dot-separated and
            # non-empty. Malformed entries are ignored, never matched.
            if not host or "." not in host or host.startswith(".") or host.endswith("."):
                continue
            cleaned.add(host)
        return cls(frozenset(cleaned))

    def matches(self, hostname: str) -> bool:
        """Hostname-boundary match: exact or proper-subdomain only.

        ``example.com`` accepts ``example.com``, ``www.example.com`` (www
        is already stripped from the candidate by ``normalize_url``) and
        ``sub.example.com``; it rejects ``fakeexample.com`` and
        ``example.com.evil.example``. Pure string logic — no DNS/network.
        """
        if not hostname:
            return False
        return any(
            hostname == entry or hostname.endswith("." + entry)
            for entry in self.entries
        )


def _hostname(url: str) -> Optional[str]:
    """Hostname of an already-normalized URL, or ``None`` (IPv6 kept)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    hostname = (parts.hostname or "").strip().lower()
    return hostname or None


def _is_repo_root_url(url: str) -> bool:
    """True iff the normalized URL itself is a GitHub repository root.

    ``github.com/<owner>/<repo>`` (any trailing-slash form) — but NOT
    deep links (``/blob/``, ``/issues/`` …): an issue page is not the
    repository resource.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if (parts.hostname or "").strip().lower() != "github.com":
        return False
    segments = [segment for segment in parts.path.split("/") if segment]
    return len(segments) == 2


def _hn_native_provenance(discovery: RawDiscovery) -> bool:
    """True iff the record URL IS the HN-native post URL.

    Requires the strict boolean ``metadata["hn_native"] is True`` AND a
    usable ``metadata["hn_item_url"]`` that is the same resource as the
    record URL (compared via the shared normalizer, like dedup does).
    A string ``"true"`` or a record whose URL points elsewhere never
    qualifies.
    """
    if discovery.metadata.get("hn_native") is not True:
        return False
    item_url = discovery.metadata.get("hn_item_url")
    if not isinstance(item_url, str) or not item_url.strip():
        return False
    record = normalize_url(discovery.url)
    native = normalize_url(item_url)
    return record is not None and record == native


def _declared_github_repo(discovery: RawDiscovery) -> Optional[str]:
    """Usable ``identifiers['github_repo']`` value, or ``None``.

    Same conservative shape as dedup's identifier handling: blank or
    non-string values are ignored; the value is compared case-insensitively
    (``github_repo_identity`` returns a lowercased identity).
    """
    raw = (discovery.identifiers or {}).get("github_repo")
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value or "/" not in value:
        return None
    owner, _, repo = value.partition("/")
    if not owner or not repo:
        return None
    return f"{owner}/{repo}".lower()


def verify_provenance(
    discovery: RawDiscovery,
    source_type: SourceType,
    *,
    trusted_primary_domains: Iterable[str] = (),
) -> VerificationResult:
    """Verify the provenance of one raw discovery, deterministically.

    Decision table (evaluated top-down; first match wins):

    1. missing URL (None/blank)                      -> REJECTED
    2. URL not normalizable (scheme/host malformed)  -> REJECTED
    3. GitHub identity contradiction (GITHUB source) -> DISPUTED
    4. HN-native post (strict metadata contract)     -> VERIFIED (0.75)
    5. GitHub repository provenance                  -> VERIFIED (0.90)
    6. trusted official domain                       -> VERIFIED (0.95)
    7. HN discussion URL (not native)                -> UNVERIFIED (0.35)
    8. anything else usable                          -> UNVERIFIED (0.35)

    ``source_type`` participates ONLY in the GitHub contradiction check
    (rule 3) — a trusted-domain match verifies any source type. See the
    module docstring for the provenance-vs-fact-checking boundary.
    """
    # Rule 1 — no usable provenance identity at all.
    if discovery.url is None or not str(discovery.url).strip():
        return VerificationResult(
            verification_status=VerificationStatus.REJECTED,
            primary_source_found=False,
            primary_source_url=None,
            confidence=CONFIDENCE_REJECTED,
            notes=NOTE_REJECTED_MISSING_URL,
        )

    # Rule 2 — malformed/unsupported URL. ``normalize_url`` owns the
    # conservative scheme/host policy; its refusal is reused verbatim
    # rather than duplicated.
    normalized = normalize_url(discovery.url)
    if normalized is None:
        return VerificationResult(
            verification_status=VerificationStatus.REJECTED,
            primary_source_found=False,
            primary_source_url=None,
            confidence=CONFIDENCE_REJECTED,
            notes=NOTE_REJECTED_MALFORMED_URL,
        )

    url = normalized
    trusted = _TrustedDomains.build(trusted_primary_domains)

    # Rule 3 — explicit contradictory provenance evidence: a GitHub
    # adapter record declaring one repository while pointing at another
    # resource (non-github URL, or a DIFFERENT github repository).
    # source_type-gated so only the adapter owning the namespace can
    # trigger it; never emitted for mere low confidence.
    if source_type == SourceType.GITHUB:
        declared = _declared_github_repo(discovery)
        if declared is not None:
            url_repo = github_repo_identity(url)
            if url_repo is None or url_repo != declared:
                return VerificationResult(
                    verification_status=VerificationStatus.DISPUTED,
                    primary_source_found=False,
                    primary_source_url=None,
                    confidence=CONFIDENCE_REJECTED,
                    notes=NOTE_DISPUTED_GITHUB_IDENTITY_CONFLICT,
                )

    # Rule 4 — HN-native post: HN is the actual host of the record.
    if _hn_native_provenance(discovery):
        return VerificationResult(
            verification_status=VerificationStatus.VERIFIED,
            primary_source_found=True,
            primary_source_url=url,
            confidence=CONFIDENCE_HN_NATIVE,
            notes=NOTE_PRIMARY_HN_NATIVE,
        )

    # Rule 5a — the URL itself is the repository resource.
    if _is_repo_root_url(url):
        repo = github_repo_identity(url)
        return VerificationResult(
            verification_status=VerificationStatus.VERIFIED,
            primary_source_found=True,
            primary_source_url=f"https://github.com/{repo}",
            confidence=CONFIDENCE_GITHUB_REPOSITORY,
            notes=NOTE_PRIMARY_GITHUB_REPOSITORY,
        )

    # Rule 5b — declared repository identity corroborated by a github.com
    # URL (deep links allowed: the declaration justifies canonicalizing
    # to the repo root). For source_type == GITHUB, rule 3 has already
    # established there is no contradiction, so a matching deep link
    # verifies here too; for other source types the declaration plus a
    # matching github.com URL is the corroboration itself.
    declared = _declared_github_repo(discovery)
    if declared is not None:
        url_repo = github_repo_identity(url)
        if url_repo is not None and url_repo == declared:
            return VerificationResult(
                verification_status=VerificationStatus.VERIFIED,
                primary_source_found=True,
                primary_source_url=f"https://github.com/{declared}",
                confidence=CONFIDENCE_GITHUB_REPOSITORY,
                notes=NOTE_PRIMARY_GITHUB_REPOSITORY,
            )

    # Rule 6 — explicit trusted official domain (hostname-boundary).
    host = _hostname(url)
    if host is not None and trusted.matches(host):
        return VerificationResult(
            verification_status=VerificationStatus.VERIFIED,
            primary_source_found=True,
            primary_source_url=url,
            confidence=CONFIDENCE_OFFICIAL_TRUSTED_DOMAIN,
            notes=NOTE_PRIMARY_TRUSTED_OFFICIAL_DOMAIN,
        )

    # Rule 7 — HN discussion URL: community provenance, observable as
    # its own (still usable, unverified) class.
    if host == "news.ycombinator.com":
        return VerificationResult(
            verification_status=VerificationStatus.UNVERIFIED,
            primary_source_found=False,
            primary_source_url=None,
            confidence=CONFIDENCE_SECONDARY,
            notes=NOTE_SECONDARY_HACKER_NEWS_DISCUSSION,
        )

    # Rule 8 — generic usable secondary source. Secondary is NOT a
    # rejection: it is usable discovery material without strong
    # primary provenance.
    return VerificationResult(
        verification_status=VerificationStatus.UNVERIFIED,
        primary_source_found=False,
        primary_source_url=None,
        confidence=CONFIDENCE_SECONDARY,
        notes=NOTE_SECONDARY_UNTRUSTED_DOMAIN,
    )


__all__ = [
    "CONFIDENCE_OFFICIAL_TRUSTED_DOMAIN",
    "CONFIDENCE_GITHUB_REPOSITORY",
    "CONFIDENCE_HN_NATIVE",
    "CONFIDENCE_SECONDARY",
    "CONFIDENCE_REJECTED",
    "NOTE_PRIMARY_GITHUB_REPOSITORY",
    "NOTE_PRIMARY_TRUSTED_OFFICIAL_DOMAIN",
    "NOTE_PRIMARY_HN_NATIVE",
    "NOTE_SECONDARY_UNTRUSTED_DOMAIN",
    "NOTE_SECONDARY_HACKER_NEWS_DISCUSSION",
    "NOTE_REJECTED_MISSING_URL",
    "NOTE_REJECTED_MALFORMED_URL",
    "NOTE_DISPUTED_GITHUB_IDENTITY_CONFLICT",
    "verify_provenance",
]
