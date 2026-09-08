"""Source adapters for Researcher 2.0.

Each adapter wraps exactly one discovery source and returns raw,
source-neutral discovery records. Adapters must NOT classify, score,
deduplicate or verify — that is the Researcher pipeline's job.

Phase 1 sources: Hacker News, GitHub, curated official RSS.
Reddit is deliberately NOT scaffolded here: an adapter is added only
when OAuth integration is actually implemented (SourceType.REDDIT
already reserves the domain concept in the Stage 3.1 contracts).
"""

from src.research.adapters.base import (
    AdapterFetchResult,
    RawDiscovery,
    SourceAdapter,
)

__all__ = [
    "AdapterFetchResult",
    "RawDiscovery",
    "SourceAdapter",
]
