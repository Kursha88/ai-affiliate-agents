"""Researcher 2.0 -> legacy news_item compatibility bridge (Stage 3.2, Step 13F).

PURE COMPATIBILITY CODE. Converts an already-produced ``ResearchResult``
into the OLD ``news_item`` dict shape accepted by the existing
``create_content_plan(news_item=...)`` reads:

    news_item.get("title")
    news_item.get("source", "")
    news_item.get("url", "")
    news_item.get("age_hours", 0)

The bridge executes no pipeline. It runs no Researcher, performs no
network I/O, instantiates no adapters, and touches no DB/state/files.
It does not re-rank, re-score, classify or verify anything: it reads
ONLY the first ranked candidate of the given result and maps existing
fields into the legacy shape.
"""

from datetime import datetime

from src.research.researcher import ResearchResult

__all__ = ["research_result_to_news_item"]

_ERROR_NOW_NAIVE = "now must be timezone-aware"
_ERROR_PUBLISHED_NAIVE = "published_at must be timezone-aware"


def _is_timezone_aware(value: datetime) -> bool:
    """Return True only when ``value`` carries a usable UTC offset."""
    return value.tzinfo is not None and value.utcoffset() is not None


def research_result_to_news_item(
    result: ResearchResult,
    *,
    now: datetime,
) -> dict | None:
    """Convert the top-ranked candidate of ``result`` to a legacy news_item.

    Returns exactly ``{"title", "source", "url", "age_hours"}`` built from
    the FIRST entry of ``result.ranked.ranked`` (never re-ranked, re-scored,
    re-classified or re-verified), or ``None`` when the ranked shortlist is
    empty. Ages derive ONLY from the candidate's ``published_at`` and the
    injected ``now``; both must be timezone-aware whenever a published_at
    value exists. Future published_at values clamp the age to 0.
    """
    ranked_shortlist = result.ranked.ranked
    if not ranked_shortlist:
        return None

    ranked = ranked_shortlist[0]
    matches = [
        candidate
        for candidate in result.candidates
        if candidate.candidate_id == ranked.candidate_id
    ]
    if not matches:
        raise ValueError("ranked candidate missing from processed candidates")
    if len(matches) > 1:
        raise ValueError("duplicate processed candidate_id")
    candidate = matches[0]

    title = candidate.discovery.title
    if not isinstance(title, str) or not title.strip():
        raise ValueError("ranked candidate title is empty")

    published_at = candidate.discovery.published_at
    if published_at is None:
        age_hours = 0
    else:
        if not isinstance(now, datetime) or not _is_timezone_aware(now):
            raise ValueError(_ERROR_NOW_NAIVE)
        if isinstance(published_at, datetime):
            published_dt = published_at
        elif isinstance(published_at, str):
            # RawDiscovery.published_at is the adapter-normalized ISO string.
            published_dt = datetime.fromisoformat(published_at)
        else:
            raise ValueError(_ERROR_PUBLISHED_NAIVE)
        if not _is_timezone_aware(published_dt):
            raise ValueError(_ERROR_PUBLISHED_NAIVE)
        age = (now - published_dt).total_seconds() / 3600
        age_hours = 0 if age < 0 else round(age, 2)

    url = candidate.discovery.url
    return {
        "title": title,
        "source": candidate.source_type.value,
        "url": "" if url is None else str(url),
        "age_hours": age_hours,
    }
