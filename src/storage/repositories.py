from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from datetime import datetime
from typing import Optional, Tuple

from src.core.time_service import TimeService
from src.domain.models import (
    ContentItem,
    ContentStatus,
    PipelineRun,
    Publication,
    PublicationStatus,
    RunStatus,
)
from src.storage.database import SCHEMA_VERSION, Database


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_topic(topic: str) -> str:
    return re.sub(r"\s+", " ", topic.strip().casefold())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PipelineRunRepository:
    def __init__(self, db: Database, time: TimeService) -> None:
        self.db = db
        self.time = time

    def _row_to_model(self, row: sqlite3.Row) -> PipelineRun:
        return PipelineRun(**dict(row))

    def get(self, run_id: str) -> Optional[PipelineRun]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def get_by_external_id(self, trigger_external_id: str) -> Optional[PipelineRun]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE trigger_external_id = ?",
                (trigger_external_id,),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def start(
        self,
        mode: str,
        trigger: str,
        trigger_external_id: Optional[str] = None,
    ) -> Tuple[PipelineRun, bool]:
        if trigger_external_id:
            existing = self.get_by_external_id(trigger_external_id)
            if existing:
                return existing, False

        now = self.time.now_utc()
        now_ts = self.time.utc_timestamp(now)
        business_date = self.time.business_date(now)

        if trigger_external_id:
            run_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"pipeline_run:{trigger_external_id}",
                )
            )
        else:
            run_id = str(uuid.uuid4())

        run = PipelineRun(
            run_id=run_id,
            started_at=now_ts,
            finished_at=None,
            business_date=business_date,
            timezone=self.time.timezone_name,
            mode=mode,
            trigger=trigger,
            trigger_external_id=trigger_external_id,
            status=RunStatus.RUNNING,
            error_code=None,
            error_message=None,
            duration_seconds=None,
            schema_version=SCHEMA_VERSION,
            created_at=now_ts,
        )

        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO pipeline_runs (
                        run_id,
                        started_at,
                        finished_at,
                        business_date,
                        timezone,
                        mode,
                        trigger,
                        trigger_external_id,
                        status,
                        error_code,
                        error_message,
                        duration_seconds,
                        schema_version,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.run_id,
                        run.started_at,
                        run.finished_at,
                        run.business_date,
                        run.timezone,
                        run.mode,
                        run.trigger,
                        run.trigger_external_id,
                        run.status,
                        run.error_code,
                        run.error_message,
                        run.duration_seconds,
                        run.schema_version,
                        run.created_at,
                    ),
                )
            return run, True
        except sqlite3.IntegrityError:
            if trigger_external_id:
                existing = self.get_by_external_id(trigger_external_id)
                if existing:
                    return existing, False
            raise

    def mark_running(self, run_id: str) -> None:
        now_ts = self.time.utc_timestamp()
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE pipeline_runs
                SET
                    status = ?,
                    started_at = ?,
                    finished_at = NULL,
                    error_code = NULL,
                    error_message = NULL,
                    duration_seconds = NULL
                WHERE run_id = ?
                """,
                (RunStatus.RUNNING, now_ts, run_id),
            )

    def complete(
        self,
        run_id: str,
        status: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        run = self.get(run_id)
        if run is None:
            return

        finished_at = self.time.now_utc()
        finished_ts = self.time.utc_timestamp(finished_at)

        started = _parse_timestamp(run.started_at)
        duration_seconds = None
        if started:
            duration_seconds = max(0, int((finished_at - started).total_seconds()))

        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE pipeline_runs
                SET
                    finished_at = ?,
                    status = ?,
                    error_code = ?,
                    error_message = ?,
                    duration_seconds = ?
                WHERE run_id = ?
                """,
                (
                    finished_ts,
                    status,
                    error_code,
                    error_message,
                    duration_seconds,
                    run_id,
                ),
            )


class ContentItemRepository:
    def __init__(self, db: Database, time: TimeService) -> None:
        self.db = db
        self.time = time

    def _row_to_model(self, row: sqlite3.Row) -> ContentItem:
        return ContentItem(**dict(row))

    def get(self, content_id: str) -> Optional[ContentItem]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM content_items WHERE content_id = ?",
                (content_id,),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[ContentItem]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM content_items WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def get_or_create(
        self,
        campaign_id: str,
        content_cluster: str,
        topic: str,
        format_: str,
        language: str,
        mode: str,
        business_date: str,
        source_item_id: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> Tuple[ContentItem, bool]:
        normalized_topic = normalize_topic(topic)

        content_hash = _sha256(
            "|".join(
                [
                    mode,
                    content_cluster,
                    normalized_topic,
                    source_url or "",
                ]
            )
        )

        idempotency_key = _sha256(
            "|".join(
                [
                    mode,
                    content_cluster,
                    normalized_topic,
                    source_url or "",
                    business_date,
                ]
            )
        )

        existing = self.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing, False

        now_ts = self.time.utc_timestamp()
        content_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"content:{idempotency_key}"))

        content = ContentItem(
            content_id=content_id,
            campaign_id=campaign_id,
            content_cluster=content_cluster,
            topic=topic,
            normalized_topic=normalized_topic,
            format=format_,
            language=language,
            mode=mode,
            source_item_id=source_item_id,
            source_url=source_url,
            status=ContentStatus.SELECTED,
            idempotency_key=idempotency_key,
            content_hash=content_hash,
            business_date=business_date,
            retry_count=0,
            created_at=now_ts,
            updated_at=now_ts,
        )

        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO content_items (
                        content_id,
                        campaign_id,
                        content_cluster,
                        topic,
                        normalized_topic,
                        format,
                        language,
                        mode,
                        source_item_id,
                        source_url,
                        status,
                        idempotency_key,
                        content_hash,
                        business_date,
                        retry_count,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        content.content_id,
                        content.campaign_id,
                        content.content_cluster,
                        content.topic,
                        content.normalized_topic,
                        content.format,
                        content.language,
                        content.mode,
                        content.source_item_id,
                        content.source_url,
                        content.status,
                        content.idempotency_key,
                        content.content_hash,
                        content.business_date,
                        content.retry_count,
                        content.created_at,
                        content.updated_at,
                    ),
                )
            return content, True
        except sqlite3.IntegrityError:
            existing = self.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing, False
            raise

    def mark_published(self, content_id: str) -> None:
        now_ts = self.time.utc_timestamp()
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE content_items
                SET
                    status = ?,
                    updated_at = ?
                WHERE content_id = ?
                """,
                (ContentStatus.PUBLISHED, now_ts, content_id),
            )


class PublicationRepository:
    def __init__(self, db: Database, time: TimeService) -> None:
        self.db = db
        self.time = time

    def _row_to_model(self, row: sqlite3.Row) -> Publication:
        return Publication(**dict(row))

    def get(self, publication_id: str) -> Optional[Publication]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM publications WHERE publication_id = ?",
                (publication_id,),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def get_by_content_platform(self, content_id: str, platform: str) -> Optional[Publication]:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM publications
                WHERE content_id = ? AND platform = ?
                """,
                (content_id, platform),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Publication]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM publications WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            return self._row_to_model(row) if row else None

    def get_or_create(
        self,
        content_id: str,
        platform: str,
        business_date: str,
    ) -> Tuple[Publication, bool]:
        platform = platform.strip().lower()
        idempotency_key = _sha256(f"{content_id}:{platform}")

        existing = self.get_by_content_platform(content_id, platform)
        if existing:
            return existing, False

        existing = self.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing, False

        now_ts = self.time.utc_timestamp()
        publication_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"publication:{idempotency_key}",
            )
        )

        publication = Publication(
            publication_id=publication_id,
            content_id=content_id,
            platform=platform,
            status=PublicationStatus.PENDING,
            external_post_id=None,
            post_url=None,
            idempotency_key=idempotency_key,
            attempt_count=0,
            last_attempt_at=None,
            scheduled_at=None,
            published_at=None,
            business_date=business_date,
            slot_number=None,
            error_code=None,
            error_message=None,
            created_at=now_ts,
            updated_at=now_ts,
        )

        try:
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO publications (
                        publication_id,
                        content_id,
                        platform,
                        status,
                        external_post_id,
                        post_url,
                        idempotency_key,
                        attempt_count,
                        last_attempt_at,
                        scheduled_at,
                        published_at,
                        business_date,
                        slot_number,
                        error_code,
                        error_message,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        publication.publication_id,
                        publication.content_id,
                        publication.platform,
                        publication.status,
                        publication.external_post_id,
                        publication.post_url,
                        publication.idempotency_key,
                        publication.attempt_count,
                        publication.last_attempt_at,
                        publication.scheduled_at,
                        publication.published_at,
                        publication.business_date,
                        publication.slot_number,
                        publication.error_code,
                        publication.error_message,
                        publication.created_at,
                        publication.updated_at,
                    ),
                )
            return publication, True
        except sqlite3.IntegrityError:
            existing = self.get_by_content_platform(content_id, platform)
            if existing:
                return existing, False
            existing = self.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing, False
            raise

    def mark_in_progress(self, publication_id: str) -> None:
        now_ts = self.time.utc_timestamp()
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE publications
                SET
                    status = ?,
                    attempt_count = attempt_count + 1,
                    last_attempt_at = ?,
                    updated_at = ?
                WHERE publication_id = ?
                """,
                (
                    PublicationStatus.IN_PROGRESS,
                    now_ts,
                    now_ts,
                    publication_id,
                ),
            )

    def mark_published(
        self,
        publication_id: str,
        external_post_id: Optional[str],
        post_url: Optional[str] = None,
    ) -> None:
        now_ts = self.time.utc_timestamp()
        external_post_id = external_post_id or None

        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE publications
                SET
                    status = ?,
                    external_post_id = ?,
                    post_url = ?,
                    published_at = ?,
                    error_code = NULL,
                    error_message = NULL,
                    updated_at = ?
                WHERE publication_id = ?
                """,
                (
                    PublicationStatus.PUBLISHED,
                    external_post_id,
                    post_url,
                    now_ts,
                    now_ts,
                    publication_id,
                ),
            )

    def _set_status(
        self,
        publication_id: str,
        status: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        now_ts = self.time.utc_timestamp()
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE publications
                SET
                    status = ?,
                    error_code = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE publication_id = ?
                """,
                (
                    status,
                    error_code,
                    error_message,
                    now_ts,
                    publication_id,
                ),
            )

    def mark_failed(
        self,
        publication_id: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        self._set_status(
            publication_id=publication_id,
            status=PublicationStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
        )

    def mark_retry_pending(
        self,
        publication_id: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        self._set_status(
            publication_id=publication_id,
            status=PublicationStatus.RETRY_PENDING,
            error_code=error_code,
            error_message=error_message,
        )

    def mark_manual_review(
        self,
        publication_id: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        self._set_status(
            publication_id=publication_id,
            status=PublicationStatus.MANUAL_REVIEW,
            error_code=error_code,
            error_message=error_message,
        )

    def mark_skipped(
        self,
        publication_id: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        self._set_status(
            publication_id=publication_id,
            status=PublicationStatus.SKIPPED,
            error_code=error_code,
            error_message=error_message,
        )