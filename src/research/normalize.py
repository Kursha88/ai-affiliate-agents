"""Deterministic normalization utilities for Researcher 2.0.

Pure functions only: no network, no I/O, no state, no side effects.

Conservative philosophy: a false deduplication (two genuinely different
stories collapsed into one) is worse than a missed duplicate. Therefore:
- Only well-known tracking parameters are removed; meaningful query
  parameters are preserved verbatim.
- Generic ``ref`` parameters are deliberately preserved (GitHub branch
  links and several docs sites use ``ref`` semantically).
- Only ``www.`` is stripped from hosts; ``m.`` / ``mobile.`` subdomains
  are preserved because they may serve different content.
- URL path casing is preserved (paths are case-sensitive).
- Titles keep their original form in the caller's data; only the
  normalized match-key is produced here.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters recognized as pure trackers (name match, case-insensitive).
# Deliberately NOT included: "ref" (GitHub branch links, docs deep links),
# "tab", "id", "lang" and similar meaningful parameters.
TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "twclid",
        "yclid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "si",
        "ref_src",
        "ref_url",
        "cmpid",
        "spm",
        "scm",
    }
)

# Parameter-name prefixes recognized as trackers (e.g. utm_source, utm_campaign).
TRACKING_PARAM_PREFIXES: tuple[str, ...] = ("utm_",)

# Default ports are dropped during host normalization (identity-unsafe no-op otherwise).
_DEFAULT_PORTS: dict[str, Optional[int]] = {"http": 80, "https": 443}


def _is_tracking_param(name: str) -> bool:
    key = name.strip().lower()
    if not key:
        return False
    if any(key.startswith(prefix) for prefix in TRACKING_PARAM_PREFIXES):
        return True
    return key in TRACKING_PARAMS


def normalize_url(url: Optional[str]) -> Optional[str]:
    """Normalize a content URL for identity comparison.

    Returns ``None`` for empty input or anything that is not clearly an
    absolute http(s) URL (schemeless, ftp, malformed) — guessing would
    risk false identity matches.

    Normalizations applied:
    - lowercase scheme and host; drop userinfo; drop default ports
    - strip a leading ``www.`` (only when the remainder stays a real host)
    - remove fragments
    - remove known tracking query parameters (other parameters preserved
      verbatim, in original order)
    - strip trailing slashes from the path (``/a/`` -> ``/a``, root ``/``
      -> empty)
    - never rewrite the path itself (case and encoding preserved)
    """
    if url is None:
        return None
    candidate = str(url).strip()
    if not candidate:
        return None

    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None

    scheme = (parts.scheme or "").strip().lower()
    if scheme not in ("http", "https"):
        return None

    hostname = (parts.hostname or "").strip().lower()
    if not hostname:
        return None

    # A single trailing dot is the DNS FQDN form of the same host
    # ("example.com." and "example.com" are identical) — safe to unify
    # for identity comparison; refusing it would miss true duplicates.
    if hostname.endswith("."):
        hostname = hostname.rstrip(".")

    if ":" not in hostname and "." not in hostname:
        # Dotless host (e.g. "www", "localhost") — not a meaningful public
        # content URL; refuse rather than guess an identity. (IPv6 literals
        # contain ":" and are handled below.)
        return None

    # Strip exactly one leading "www."; keep hosts like "www.com" intact
    # (stripping must leave a dotted domain behind).
    if hostname.startswith("www.") and "." in hostname[4:]:
        hostname = hostname[4:]

    try:
        port = parts.port
    except ValueError:
        return None

    if ":" in hostname and not hostname.startswith("["):
        # IPv6 literal — reassemble with brackets.
        host_display = f"[{hostname}]"
    else:
        host_display = hostname

    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host_display}:{port}"
    else:
        netloc = host_display

    path = parts.path or ""
    if path == "/":
        # Root path denotes the same resource as no path at all
        # ("https://example.com/" and "https://example.com" are identical).
        path = ""
    elif len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Preserve the original query string verbatim unless a tracking
    # parameter must be removed (avoids re-encoding churn).
    query = parts.query
    if query:
        pairs = parse_qsl(query, keep_blank_values=True)
        if any(_is_tracking_param(name) for name, _ in pairs):
            kept = [(n, v) for (n, v) in pairs if not _is_tracking_param(n)]
            query = urlencode(kept)

    return urlunsplit((scheme, netloc, path, query, ""))


def url_identity(url: Optional[str]) -> Optional[str]:
    """Canonical identity for a generic content URL (its normalized form).

    Two URLs share identity iff their normalized forms are equal.
    Returns ``None`` when the URL cannot be normalized.
    """
    return normalize_url(url)


def github_repo_identity(url: Optional[str]) -> Optional[str]:
    """Canonical GitHub repository identity: ``owner/repo`` (lowercased).

    Returned only when the URL clearly identifies a repository:
    ``github.com/<owner>/<repo>[/<anything>]`` — ``blob``/``tree``/
    ``issues``/``releases`` deep links all resolve to the same identity.
    The ``.git`` suffix is stripped. Returns ``None`` for non-GitHub
    URLs, user-only paths, gists and unparseable input.
    """
    normalized = normalize_url(url)
    if normalized is None:
        return None

    parts = urlsplit(normalized)
    if (parts.hostname or "") != "github.com":
        return None

    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) < 2:
        return None

    owner, repo = segments[0], segments[1]
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        return None

    return f"{owner}/{repo}".lower()


# Punctuation variant unification for title matching (conservative:
# quotes/dashes/ellipsis only — never deletes information-bearing
# punctuation like "." in version numbers).
_TITLE_CHAR_MAP: dict[str, str] = {
    "\u2018": "'",  # left single curly quote
    "\u2019": "'",  # right single curly quote
    "\u201a": "'",  # single low quote
    "\u02bc": "'",  # modifier letter apostrophe
    "\u201c": '"',  # left double curly quote
    "\u201d": '"',  # right double curly quote
    "\u201e": '"',  # double low quote
    "\u00ab": '"',  # left guillemet
    "\u00bb": '"',  # right guillemet
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2212": "-",  # minus sign
    "\u2026": "...",  # horizontal ellipsis
    "\u00a0": " ",  # no-break space
}


def normalize_title(title: Optional[str]) -> str:
    """Produce a dedup match-key for a title (original is kept by caller).

    Unicode-safe: NFKC folding, punctuation-variant unification,
    casefold, whitespace collapse. Punctuation is normalized
    conservatively (variants mapped to ASCII), never stripped wholesale.
    Returns ``""`` for empty input.
    """
    if not title:
        return ""

    text = unicodedata.normalize("NFKC", str(title))
    for source, replacement in _TITLE_CHAR_MAP.items():
        text = text.replace(source, replacement)

    text = text.casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return text


__all__ = [
    "TRACKING_PARAMS",
    "TRACKING_PARAM_PREFIXES",
    "normalize_url",
    "url_identity",
    "github_repo_identity",
    "normalize_title",
]
