"""Platform adaptation domain contracts (Stage 18A).

Contracts only:

    AdaptationSourceContent + PlatformAdaptationSpec
        -> (future adaptation boundary)
        -> PlatformContentVariant

No adaptation logic, no platform policy, no validation, no persistence.
A future Creation boundary produces AdaptationSourceContent; a future 18B
deterministic policy produces PlatformAdaptationSpec per platform.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Optional, Tuple

from src.domain.strategy import TargetPlatform

__all__ = [
    "AdaptationContentKind",
    "AdaptationSourceContent",
    "PlatformAdaptationSpec",
    "PlatformContentVariant",
]


class AdaptationContentKind(StrEnum):
    """Shape of textual platform-adapted content."""

    TEXT_POST = "text_post"
    SHORT_VIDEO_SCRIPT = "short_video_script"
    PIN_COPY = "pin_copy"


@dataclass(frozen=True)
class AdaptationSourceContent:
    """Canonical already-created content consumed by platform adaptation."""

    content_id: str
    candidate_id: str
    title: str
    body: str
    cta: str
    cta_link: str
    language: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class PlatformAdaptationSpec:
    """Deterministic adaptation policy output for exactly one platform."""

    platform: TargetPlatform
    content_kind: AdaptationContentKind
    max_characters: Optional[int]
    requires_title: bool
    allows_external_link: bool
    structure: Tuple[str, ...]
    tone: str


@dataclass(frozen=True)
class PlatformContentVariant:
    """Platform-native textual variant produced by adaptation."""

    variant_id: str
    candidate_id: str
    source_content_id: str
    platform: TargetPlatform
    content_kind: AdaptationContentKind
    title: str
    body: str
    cta: str
    cta_link: str
    language: str
    metadata: Mapping[str, Any]
