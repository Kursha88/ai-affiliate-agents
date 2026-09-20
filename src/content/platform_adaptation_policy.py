"""Deterministic platform adaptation policy (Stage 18B).

Pure policy layer:

    TargetPlatform -> PlatformAdaptationSpec

Policy data only: no content access, no truncation, no validation, no
publishing. Unknown/non-member platform input fails naturally through
direct dict indexing.
"""

from typing import Tuple

from src.domain.platform_adaptation import (
    AdaptationContentKind,
    PlatformAdaptationSpec,
)
from src.domain.strategy import TargetPlatform

__all__ = [
    "get_platform_adaptation_spec",
    "get_platform_adaptation_specs",
]

_PLATFORM_ADAPTATION_POLICY: dict[TargetPlatform, PlatformAdaptationSpec] = {
    TargetPlatform.TELEGRAM: PlatformAdaptationSpec(
        platform=TargetPlatform.TELEGRAM,
        content_kind=AdaptationContentKind.TEXT_POST,
        max_characters=None,
        requires_title=True,
        allows_external_link=True,
        structure=(
            "hook",
            "context",
            "value",
            "cta",
        ),
        tone="concise and practical",
    ),
    TargetPlatform.X: PlatformAdaptationSpec(
        platform=TargetPlatform.X,
        content_kind=AdaptationContentKind.TEXT_POST,
        max_characters=280,
        requires_title=False,
        allows_external_link=True,
        structure=(
            "hook",
            "value",
            "cta",
        ),
        tone="sharp and concise",
    ),
    TargetPlatform.LINKEDIN: PlatformAdaptationSpec(
        platform=TargetPlatform.LINKEDIN,
        content_kind=AdaptationContentKind.TEXT_POST,
        max_characters=3000,
        requires_title=False,
        allows_external_link=True,
        structure=(
            "hook",
            "context",
            "insight",
            "practical_takeaway",
            "cta",
        ),
        tone="professional and practical",
    ),
    TargetPlatform.REDDIT: PlatformAdaptationSpec(
        platform=TargetPlatform.REDDIT,
        content_kind=AdaptationContentKind.TEXT_POST,
        max_characters=None,
        requires_title=True,
        allows_external_link=False,
        structure=(
            "title",
            "context",
            "details",
            "discussion",
        ),
        tone="informative and conversational",
    ),
    TargetPlatform.YOUTUBE_SHORTS: PlatformAdaptationSpec(
        platform=TargetPlatform.YOUTUBE_SHORTS,
        content_kind=AdaptationContentKind.SHORT_VIDEO_SCRIPT,
        max_characters=None,
        requires_title=True,
        allows_external_link=False,
        structure=(
            "hook",
            "setup",
            "value",
            "payoff",
        ),
        tone="fast-paced and clear",
    ),
    TargetPlatform.TIKTOK: PlatformAdaptationSpec(
        platform=TargetPlatform.TIKTOK,
        content_kind=AdaptationContentKind.SHORT_VIDEO_SCRIPT,
        max_characters=None,
        requires_title=False,
        allows_external_link=False,
        structure=(
            "hook",
            "setup",
            "value",
            "payoff",
        ),
        tone="direct and energetic",
    ),
    TargetPlatform.PINTEREST: PlatformAdaptationSpec(
        platform=TargetPlatform.PINTEREST,
        content_kind=AdaptationContentKind.PIN_COPY,
        max_characters=500,
        requires_title=True,
        allows_external_link=True,
        structure=(
            "title",
            "description",
            "cta",
        ),
        tone="descriptive and actionable",
    ),
}


def get_platform_adaptation_spec(
    platform: TargetPlatform,
) -> PlatformAdaptationSpec:
    return _PLATFORM_ADAPTATION_POLICY[platform]


def get_platform_adaptation_specs(
    platforms: Tuple[TargetPlatform, ...],
) -> Tuple[PlatformAdaptationSpec, ...]:
    return tuple(
        get_platform_adaptation_spec(platform)
        for platform in platforms
    )
