"""Live wiring layer for Researcher 2.0 (Stage 3.2, Step 13A).

Wiring ONLY. This module composes the existing pieces into a live
``Researcher`` and runs it — nothing else:

    build_live_researcher()  ->  construct adapters + Researcher
    run_live_research()      ->  build once, run once, return unchanged

Hard boundaries (all structurally tested):

- Construction only: ``build_live_researcher`` never calls ``fetch()``,
  ``safe_fetch()`` or ``Researcher.run()``; it performs no network
  requests, reads no environment variables, config files or filesystem
  files, uses no clock, logs nothing and prints nothing.
- ``run_live_research`` calls ``build_live_researcher`` exactly once,
  then ``Researcher.run(now=..., limit=...)`` exactly once, and returns
  the result unchanged: no exception catching, no transformation, no
  fallback results, no business logic.
- Adapter order is fixed: Hacker News, GitHub, then Official Blog RSS
  (only when ``blog_feeds`` is non-empty), then Official Docs RSS (only
  when ``docs_feeds`` is non-empty).
- No CLI/``__main__`` block, no feature flags, no persistence, and no
  imports of the legacy pipeline (main/agents/publisher/strategist/
  copywriter/editor/designer), storage, state, ``requests``, ``os``,
  ``dotenv``, ``yaml`` or ``sqlite3``.

Feeds are explicitly configured ``OfficialFeed`` instances supplied by
the caller; trusted domains are forwarded unchanged (as a tuple) into
the ``Researcher`` constructor, where the existing trust-combination
logic applies. This module hardcodes no feeds and no vendor domains.
"""

from __future__ import annotations

from datetime import datetime
from typing import Collection, List, Sequence

from src.domain.strategy import SourceType
from src.research.adapters.github import GitHubAdapter
from src.research.adapters.hacker_news import HackerNewsAdapter
from src.research.adapters.rss import OfficialFeed, OfficialRssAdapter
from src.research.rank import DEFAULT_LIMIT
from src.research.researcher import ResearchResult, Researcher

__all__ = [
    "build_live_researcher",
    "run_live_research",
]


def build_live_researcher(
    *,
    blog_feeds: Sequence[OfficialFeed] = (),
    docs_feeds: Sequence[OfficialFeed] = (),
    trusted_primary_domains: Collection[str] = (),
) -> Researcher:
    """Construct the live Researcher with the fixed adapter order.

    HN and GitHub are always present; each RSS adapter is appended only
    when its feed group is non-empty. Construction only — no fetching,
    no clock, no I/O of any kind.
    """
    adapters: List[object] = []
    adapters.append(HackerNewsAdapter())
    adapters.append(GitHubAdapter())
    if blog_feeds:
        adapters.append(
            OfficialRssAdapter(
                feeds=tuple(blog_feeds),
                source_type=SourceType.OFFICIAL_BLOG,
            )
        )
    if docs_feeds:
        adapters.append(
            OfficialRssAdapter(
                feeds=tuple(docs_feeds),
                source_type=SourceType.OFFICIAL_DOCS,
            )
        )
    return Researcher(
        adapters=tuple(adapters),
        trusted_primary_domains=tuple(trusted_primary_domains),
    )


def run_live_research(
    *,
    now: datetime,
    limit: int = DEFAULT_LIMIT,
    blog_feeds: Sequence[OfficialFeed] = (),
    docs_feeds: Sequence[OfficialFeed] = (),
    trusted_primary_domains: Collection[str] = (),
) -> ResearchResult:
    """Build the live Researcher once and run it once.

    ``now`` is REQUIRED (no hidden clock). The ``ResearchResult`` is
    returned unchanged: no transformation, no fallback, no exception
    handling, no business logic.
    """
    researcher = build_live_researcher(
        blog_feeds=blog_feeds,
        docs_feeds=docs_feeds,
        trusted_primary_domains=trusted_primary_domains,
    )
    return researcher.run(now=now, limit=limit)
