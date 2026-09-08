from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class RunStatus:
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ContentStatus:
    SELECTED = "SELECTED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class PublicationStatus:
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class PipelineRun:
    run_id: str
    started_at: str
    finished_at: Optional[str]
    business_date: str
    timezone: str
    mode: str
    trigger: str
    trigger_external_id: Optional[str]
    status: str
    error_code: Optional[str]
    error_message: Optional[str]
    duration_seconds: Optional[int]
    schema_version: int
    created_at: str


@dataclass(frozen=True)
class ContentItem:
    content_id: str
    campaign_id: str
    content_cluster: str
    topic: str
    normalized_topic: str
    format: str
    language: str
    mode: str
    source_item_id: Optional[str]
    source_url: Optional[str]
    status: str
    idempotency_key: str
    content_hash: str
    business_date: str
    retry_count: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Publication:
    publication_id: str
    content_id: str
    platform: str
    status: str
    external_post_id: Optional[str]
    post_url: Optional[str]
    idempotency_key: str
    attempt_count: int
    last_attempt_at: Optional[str]
    scheduled_at: Optional[str]
    published_at: Optional[str]
    business_date: str
    slot_number: Optional[int]
    error_code: Optional[str]
    error_message: Optional[str]
    created_at: str
    updated_at: str