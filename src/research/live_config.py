"""Pure configuration model for the live Researcher wiring (Stage 3.2, Step 13B).

Converts an ALREADY-LOADED Python mapping (the research section itself —
no outer ``"research"`` key) into the exact arguments consumed by
``build_live_researcher()`` / ``run_live_research()``:

    LiveResearchConfig.from_mapping(section).live_kwargs()

This module is a PURE parser/model only:

- It does NOT read YAML, files, or environment variables.
- It performs NO network calls and NO DNS lookups.
- It does NOT construct adapters, does NOT import or run the
  ``Researcher``, and never calls ``build_live_researcher()`` or
  ``run_live_research()``.
- No clock, no logging, no printing.

Design decisions (final):

- ``OfficialFeed`` remains the single validator for feed entries: this
  parser checks only the SHAPE of the configuration (required keys,
  no unknown keys, correct container types) and lets ``OfficialFeed``
  validate ``name`` / ``feed_url`` / ``trusted_domain`` itself. Its
  ``ValueError`` propagates UNCHANGED — configuration normalization
  must not swallow or rebrand the domain model's own errors.
- Trusted domains are conservatively normalized here (strip, lowercase,
  one leading ``www.`` removed) and must be dotted hostnames free of
  scheme/path/credential/port characters. Invalid domains raise
  ``ValueError`` — a silently useless trusted set is never acceptable.
  Deduplication happens AFTER normalization, first occurrence first.
- Feed lists preserve input order and are deliberately NOT
  deduplicated: configuring the same feed twice is editorial intent
  this layer must not silently alter.
- Unknown top-level keys are rejected (fail-fast against typos in a
  config file) instead of being ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from src.research.adapters.rss import OfficialFeed

__all__ = ["LiveResearchConfig"]

#: The ONLY top-level keys accepted in the research section.
ALLOWED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {"trusted_primary_domains", "official_blog_feeds", "official_docs_feeds"}
)

#: The EXACT semantic fields every feed mapping must carry.
REQUIRED_FEED_KEYS: frozenset[str] = frozenset(
    {"name", "feed_url", "trusted_domain"}
)

#: Substrings that can never appear in a bare hostname (scheme, path,
#: query, fragment, credentials, port).
FORBIDDEN_DOMAIN_MARKERS: Tuple[str, ...] = ("://", "/", "?", "#", "@", ":")


def _normalize_trusted_domain(value: Any) -> str:
    """Normalize ONE configured trusted domain, conservatively.

    Strip whitespace, lowercase, remove one leading ``www.``; reject
    blank values, forbidden markers, and non-dotted hostnames. No DNS
    lookup, no guessing.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"trusted domain must be a string, got {type(value).__name__}: {value!r}"
        )
    host = value.strip().lower()
    if not host:
        raise ValueError("trusted domain must not be blank")
    for marker in FORBIDDEN_DOMAIN_MARKERS:
        if marker in host:
            raise ValueError(
                f"trusted domain must be a bare hostname "
                f"(no scheme/path/credentials/port), got {value!r}"
            )
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        raise ValueError(
            f"trusted domain must be a dotted hostname, got {value!r}"
        )
    return host


def _parse_trusted_domains(value: Any) -> Tuple[str, ...]:
    """Parse the trusted-domain list: normalize, dedupe, keep order."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(
            f"trusted_primary_domains must be a list or tuple, "
            f"got {type(value).__name__}"
        )
    seen: set[str] = set()
    ordered: list[str] = []
    for item in value:
        domain = _normalize_trusted_domain(item)
        if domain not in seen:
            seen.add(domain)
            ordered.append(domain)
    return tuple(ordered)


def _parse_feeds(value: Any, label: str) -> Tuple[OfficialFeed, ...]:
    """Parse one feed group into ``OfficialFeed`` instances.

    Shape checks only (list/tuple of mappings with exactly the required
    keys); value validation belongs to ``OfficialFeed`` and its errors
    propagate unchanged. Input order is preserved; duplicates are NOT
    removed.
    """
    if not isinstance(value, (list, tuple)):
        raise ValueError(
            f"{label} must be a list or tuple, got {type(value).__name__}"
        )
    feeds: list[OfficialFeed] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            raise ValueError(
                f"{label}[{index}] must be a mapping, got {type(entry).__name__}"
            )
        keys = set(entry.keys())
        missing = REQUIRED_FEED_KEYS - keys
        if missing:
            raise ValueError(
                f"{label}[{index}] is missing required fields: {sorted(missing)}"
            )
        unknown = keys - REQUIRED_FEED_KEYS
        if unknown:
            raise ValueError(
                f"{label}[{index}] contains unknown keys: {sorted(map(str, unknown))}"
            )
        feeds.append(
            OfficialFeed(
                name=entry["name"],
                feed_url=entry["feed_url"],
                trusted_domain=entry["trusted_domain"],
            )
        )
    return tuple(feeds)


@dataclass(frozen=True)
class LiveResearchConfig:
    """Parsed, normalized research configuration (immutable)."""

    blog_feeds: Tuple[OfficialFeed, ...]
    docs_feeds: Tuple[OfficialFeed, ...]
    trusted_primary_domains: Tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "LiveResearchConfig":
        """Parse the research section itself (no outer ``research`` key).

        Missing keys mean empty tuples — an empty mapping is valid.
        Unknown top-level keys and malformed values raise ``ValueError``.
        """
        if not isinstance(data, Mapping):
            raise ValueError(
                f"research config must be a mapping, got {type(data).__name__}"
            )
        unknown = set(data.keys()) - ALLOWED_TOP_LEVEL_KEYS
        if unknown:
            raise ValueError(
                f"unknown top-level research config keys: {sorted(map(str, unknown))}"
            )
        return cls(
            blog_feeds=_parse_feeds(
                data.get("official_blog_feeds", ()), "official_blog_feeds"
            ),
            docs_feeds=_parse_feeds(
                data.get("official_docs_feeds", ()), "official_docs_feeds"
            ),
            trusted_primary_domains=_parse_trusted_domains(
                data.get("trusted_primary_domains", ())
            ),
        )

    def live_kwargs(self) -> dict[str, object]:
        """Keyword arguments for the live wiring entry points.

        Exactly the three config keys — never ``now``, ``limit``,
        ``adapters`` or ``source_type``. A NEW dict is returned on every
        call so callers cannot mutate shared state.
        """
        return {
            "blog_feeds": self.blog_feeds,
            "docs_feeds": self.docs_feeds,
            "trusted_primary_domains": self.trusted_primary_domains,
        }
