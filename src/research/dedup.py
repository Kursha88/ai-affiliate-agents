"""Conservative deterministic deduplication for raw discoveries (Stage 3.2).

CORE PRINCIPLE: a false deduplication (two genuinely independent
discoveries collapsed into one) is worse than a missed duplicate.
Different sources covering the same event are NOT automatically
duplicates — independent provenance is preserved for the later VERIFY
stage.

Identity layers, applied in strict precedence order per record:

1. ``native_identifier`` — source-native identifiers from
   ``RawDiscovery.identifiers`` (e.g. ``hn_item_id``, ``github_repo``).
   Strongest identity. Compared only within compatible namespaces:
   identity is ``(identifier_key, value)``, so ``hn_item_id=123`` can
   never collide with an unrelated generic ``id=123``. Generic keys
   (``IGNORED_IDENTIFIER_KEYS``) and malformed values are ignored
   conservatively rather than guessed.
2. ``canonical_url_same_source`` — same conservative canonical URL
   (``normalize.url_identity``) AND the exact same non-blank
   ``source_name``. Records from different sources sharing a URL are
   NEVER collapsed here: same URL across different provenance is
   independent coverage (e.g. an HN story and the official blog post
   about the same announcement).

   Native-ID precedence guard (Stage 3.2, Step 5.1): the URL layer must
   NOT override explicit native-ID distinction. When BOTH records
   declare usable identifiers in the SAME strong namespace and the
   values differ (``hn_item_id=111`` vs ``hn_item_id=222``, or future
   ``reddit_post_id=a`` vs ``reddit_post_id=b``), the records are
   distinct source records by the source's own declaration and are
   preserved. A record with no usable native ID (or IDs only in
   unrelated namespaces) still collapses by canonical URL within the
   same source — there is no conflicting second native identity.
   Unrelated namespaces never create a conflict. When a record is
   collapsed (for any reason), its identifiers merge into the kept
   position's namespace map, so a later record carrying a conflicting
   native ID stays protected.
3. ``exact_title_same_source`` — weak last resort: exact
   ``normalize_title`` equality AND same non-blank ``source_name`` AND
   the record has NO usable native identifier AND NO usable URL. No
   fuzzy matching of any kind (no Levenshtein, no embeddings, no
   SequenceMatcher, no LLM) — fuzzy similarity creates false dedup and
   is deliberately absent.

GitHub rule: ``github_repo_identity()`` is intentionally NOT used here.
Repository identity is honored only when an adapter explicitly declares
``identifiers["github_repo"]`` (i.e. the record itself represents that
repository); equivalence is never inferred from URLs or metadata.

Order: stable input order; the first occurrence wins. Deterministic:
same input produces exactly the same output and duplicate groups. No
ranking or editorial quality belongs here.

Boundaries: no network/DB I/O, no classification/scoring/ranking, no
``DiscoveryCandidate`` construction, ``RawDiscovery`` never mutated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

from src.research.adapters.base import RawDiscovery
from src.research.normalize import normalize_title, url_identity

#: Reason codes (observable in ``DuplicateGroup.reason``).
REASON_NATIVE_IDENTIFIER: str = "native_identifier"
REASON_CANONICAL_URL_SAME_SOURCE: str = "canonical_url_same_source"
REASON_EXACT_TITLE_SAME_SOURCE: str = "exact_title_same_source"

#: Identifier keys too generic to be safe namespaces. A value stored
#: under one of these keys is ignored entirely: ``id=123`` must never
#: collide with ``hn_item_id=123`` from an unrelated source.
IGNORED_IDENTIFIER_KEYS: FrozenSet[str] = frozenset({"id", "key", "uid"})


def _has_id_conflict(
    usable_ids: List[Tuple[str, str]],
    known: Dict[str, str],
) -> bool:
    """True when a shared identifier namespace holds differing values.

    Compares only namespaces present on BOTH records — unrelated
    namespaces never create a conflict (Step 5.1).
    """
    for namespace, value in usable_ids:
        known_value = known.get(namespace)
        if known_value is not None and known_value != value:
            return True
    return False


def _usable_identifier(key: str, raw_value: Any) -> Optional[Tuple[str, str]]:
    """Return a safe ``(namespace, value)`` pair, or ``None`` to ignore.

    Conservative: blank/generic keys and blank/malformed values never
    produce identity. Integer values are tolerated (JSON sources) by
    stringification — same declared identity, not a guess.
    """
    if not isinstance(key, str):
        return None
    namespace = key.strip()
    if not namespace or namespace.lower() in IGNORED_IDENTIFIER_KEYS:
        return None
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, int):
        raw_value = str(raw_value)
    if not isinstance(raw_value, str):
        return None
    value = raw_value.strip()
    if not value:
        return None
    return (namespace, value)


@dataclass(frozen=True)
class DuplicateGroup:
    """One collapse decision: a kept record and its removed duplicates."""

    reason: str
    identity_key: str
    kept_index: int
    kept: RawDiscovery
    removed_indexes: Tuple[int, ...]
    removed: Tuple[RawDiscovery, ...]


@dataclass(frozen=True)
class DeduplicationResult:
    """Outcome of one deduplication pass (fully observable)."""

    items: Tuple[RawDiscovery, ...]
    duplicate_groups: Tuple[DuplicateGroup, ...]
    input_count: int
    output_count: int
    duplicate_count: int


@dataclass
class _GroupState:
    """Mutable accumulator for one duplicate group (frozen at the end)."""

    reason: str
    identity_key: str
    kept_index: int
    kept: RawDiscovery
    removed_indexes: List[int] = field(default_factory=list)
    removed: List[RawDiscovery] = field(default_factory=list)


def deduplicate(discoveries: Iterable[RawDiscovery]) -> DeduplicationResult:
    """Remove clear duplicate discovery records, conservatively.

    Stable, deterministic, side-effect free. See the module docstring
    for the identity-layer contract.
    """
    items = list(discoveries)

    kept: List[Tuple[int, RawDiscovery]] = []
    native_index: Dict[Tuple[str, str], int] = {}
    url_index: Dict[Tuple[str, str], int] = {}
    title_index: Dict[Tuple[str, str], int] = {}
    native_namespaces: Dict[int, Dict[str, str]] = {}
    groups: Dict[int, _GroupState] = {}

    for index, item in enumerate(items):
        usable_ids: List[Tuple[str, str]] = []
        for key, raw_value in (item.identifiers or {}).items():
            usable = _usable_identifier(key, raw_value)
            if usable is not None:
                usable_ids.append(usable)

        canonical_url = url_identity(item.url)
        source_key = (item.source_name or "").strip()

        match: Optional[Tuple[int, str, str]] = None

        # Layer 1 — source-native identifier (strongest, namespaced).
        if match is None:
            for namespace, value in usable_ids:
                position = native_index.get((namespace, value))
                if position is not None:
                    match = (
                        position,
                        REASON_NATIVE_IDENTIFIER,
                        f"{namespace}={value}",
                    )
                    break

        # Layer 2 — canonical URL within the same provenance only.
        # Refused when both records declare DIFFERENT values in a shared
        # strong identifier namespace: distinct native IDs are explicit
        # evidence that the source considers the records distinct.
        if match is None and canonical_url is not None and source_key:
            position = url_index.get((source_key, canonical_url))
            if position is not None and not _has_id_conflict(
                usable_ids, native_namespaces.get(position, {})
            ):
                match = (
                    position,
                    REASON_CANONICAL_URL_SAME_SOURCE,
                    f"canonical_url={canonical_url}",
                )

        # Layer 3 — exact title fallback, only with no ID and no URL.
        if match is None and not usable_ids and canonical_url is None and source_key:
            title_key = normalize_title(item.title)
            if title_key:
                position = title_index.get((source_key, title_key))
                if position is not None:
                    match = (
                        position,
                        REASON_EXACT_TITLE_SAME_SOURCE,
                        f"exact_title={title_key}",
                    )

        if match is None:
            position = len(kept)
            kept.append((index, item))
            known = native_namespaces.setdefault(position, {})
            for namespace, value in usable_ids:
                native_index.setdefault((namespace, value), position)
                known.setdefault(namespace, value)
            if canonical_url is not None and source_key:
                url_index.setdefault((source_key, canonical_url), position)
            if not usable_ids and canonical_url is None and source_key:
                title_key = normalize_title(item.title)
                if title_key:
                    title_index.setdefault((source_key, title_key), position)
        else:
            kept_position, reason, identity_key = match
            group = groups.get(kept_position)
            if group is None:
                kept_index, kept_item = kept[kept_position]
                group = _GroupState(reason, identity_key, kept_index, kept_item)
                groups[kept_position] = group
            group.removed_indexes.append(index)
            group.removed.append(item)
            # Merge the removed record's identifiers into the kept
            # position's namespace map so a later record carrying a
            # conflicting native ID stays protected (Step 5.1).
            known = native_namespaces.setdefault(kept_position, {})
            for namespace, value in usable_ids:
                known.setdefault(namespace, value)

    duplicate_groups = tuple(
        DuplicateGroup(
            reason=group.reason,
            identity_key=group.identity_key,
            kept_index=group.kept_index,
            kept=group.kept,
            removed_indexes=tuple(group.removed_indexes),
            removed=tuple(group.removed),
        )
        for _, group in sorted(groups.items())
    )
    return DeduplicationResult(
        items=tuple(item for _, item in kept),
        duplicate_groups=duplicate_groups,
        input_count=len(items),
        output_count=len(kept),
        duplicate_count=len(items) - len(kept),
    )


__all__ = [
    "REASON_NATIVE_IDENTIFIER",
    "REASON_CANONICAL_URL_SAME_SOURCE",
    "REASON_EXACT_TITLE_SAME_SOURCE",
    "IGNORED_IDENTIFIER_KEYS",
    "DuplicateGroup",
    "DeduplicationResult",
    "deduplicate",
]
