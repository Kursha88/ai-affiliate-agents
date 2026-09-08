from __future__ import annotations

from typing import Optional, Tuple

from src.core.config import Config
from src.core.time_service import TimeService
from src.domain.models import (
    ContentItem,
    PipelineRun,
    Publication,
    PublicationStatus,
    RunStatus,
)
from src.storage.database import Database
from src.storage.repositories import (
    ContentItemRepository,
    PipelineRunRepository,
    PublicationRepository,
)

class StateService:
    """
    Минимальный state layer для текущего этапа.

    Не переписывает существующий pipeline, а добавляет:
    - PipelineRun;
    - ContentItem;
    - Publication;
    - idempotency;
    - Europe/Kyiv business date.
    """

    def __init__(
        self,
        database_path: Optional[str] = None,
        timezone_name: Optional[str] = None,
    ) -> None:
        self.time = TimeService(timezone_name or Config.get_business_timezone())
        self.db = Database(database_path or Config.get_database_path())
        self.db.initialize()

        self.runs = PipelineRunRepository(self.db, self.time)
        self.contents = ContentItemRepository(self.db, self.time)
        self.publications = PublicationRepository(self.db, self.time)

    # ─── Pipeline runs ────────────────────────────────────────

    def start_pipeline_run(
        self,
        mode: str,
        trigger: str,
        trigger_external_id: Optional[str] = None,
    ) -> Tuple[PipelineRun, bool]:
        return self.runs.start(
            mode=mode,
            trigger=trigger,
            trigger_external_id=trigger_external_id,
        )

    def resume_run(self, run_id: str) -> None:
        self.runs.mark_running(run_id)

    def complete_run(self, run_id: str) -> None:
        self.runs.complete(run_id=run_id, status=RunStatus.COMPLETED)

    def fail_run(
        self,
        run_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        self.runs.complete(
            run_id=run_id,
            status=RunStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
        )

    # ─── Content items ────────────────────────────────────────

    def get_or_create_content_from_plan(
        self,
        plan: dict,
        business_date: Optional[str] = None,
    ) -> Tuple[ContentItem, bool]:
        topic = str(plan.get("topic", "")).strip()
        if not topic:
            raise ValueError("Content plan must contain non-empty topic")

        mode = str(plan.get("mode", "growth")).strip().lower()
        content_cluster = str(plan.get("content_cluster", "general")).strip().lower()
        format_ = str(plan.get("format", "unknown")).strip()
        language = str(plan.get("language", "ru")).strip()

        news = plan.get("news") or {}
        source_url = news.get("url") or None

        business_date = business_date or self.time.business_date()
        campaign_id = str(plan.get("campaign_id") or f"{mode}-{business_date}")

        return self.contents.get_or_create(
            campaign_id=campaign_id,
            content_cluster=content_cluster,
            topic=topic,
            format_=format_,
            language=language,
            mode=mode,
            business_date=business_date,
            source_item_id=None,
            source_url=source_url,
        )

    def mark_content_published(self, content_id: str) -> None:
        self.contents.mark_published(content_id)

    # ─── Publications ─────────────────────────────────────────

    def get_or_create_publication(
        self,
        content_id: str,
        platform: str,
        business_date: Optional[str] = None,
    ) -> Tuple[Publication, bool]:
        business_date = business_date or self.time.business_date()
        return self.publications.get_or_create(
            content_id=content_id,
            platform=platform,
            business_date=business_date,
        )

    def guard_publication(self, publication: Publication) -> Tuple[bool, str]:
        """
        Проверяет, можно ли выполнять публикацию.

        Всегда перечитывает актуальное состояние из базы,
        чтобы не доверять устаревшей копии объекта.

        Возвращает:
            (allowed, reason)
        """
        actual = self.publications.get(publication.publication_id)
        if actual is not None:
            publication = actual

        if publication.status == PublicationStatus.PUBLISHED:
            return False, "already_published"

        if publication.external_post_id:
            return False, "already_published"

        if publication.status == PublicationStatus.IN_PROGRESS:
            # Процесс мог упасть после отправки запроса, но до получения результата.
            # В этом случае безопаснее не повторять автоматически.
            self.publications.mark_manual_review(
                publication_id=publication.publication_id,
                error_code="INTERRUPTED_ATTEMPT",
                error_message="Previous publication attempt was interrupted before result was stored",
            )
            return False, "manual_review"

        if publication.status == PublicationStatus.MANUAL_REVIEW:
            return False, "manual_review"

        if publication.status == PublicationStatus.SKIPPED:
            return False, "skipped"

        return True, "ok"

    def begin_publication(self, publication_id: str) -> None:
        self.publications.mark_in_progress(publication_id)

    def mark_publication_published(
        self,
        publication_id: str,
        external_post_id: Optional[str],
        post_url: Optional[str] = None,
    ) -> None:
        self.publications.mark_published(
            publication_id=publication_id,
            external_post_id=external_post_id,
            post_url=post_url,
        )

    def mark_publication_failed(
        self,
        publication_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        self.publications.mark_failed(
            publication_id=publication_id,
            error_code=error_code,
            error_message=error_message,
        )

    def mark_publication_retry_pending(
        self,
        publication_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        self.publications.mark_retry_pending(
            publication_id=publication_id,
            error_code=error_code,
            error_message=error_message,
        )

    def mark_publication_manual_review(
        self,
        publication_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        self.publications.mark_manual_review(
            publication_id=publication_id,
            error_code=error_code,
            error_message=error_message,
        )

    def handle_publication_error(self, publication_id: str, error_message: str) -> None:
        if self.is_transient_error(error_message):
            self.mark_publication_retry_pending(
                publication_id=publication_id,
                error_code="TRANSIENT_ERROR",
                error_message=error_message,
            )
        else:
            self.mark_publication_failed(
                publication_id=publication_id,
                error_code="PUBLISH_FAILED",
                error_message=error_message,
            )

    @staticmethod
    def is_transient_error(error_message: str) -> bool:
        text = str(error_message or "").lower()
        markers = (
            "timeout",
            "timed out",
            "temporary",
            "network",
            "connection",
            "unavailable",
            "429",
            "502",
            "503",
            "504",
            "rate limit",
            "flood",
        )
        return any(marker in text for marker in markers)

    def build_telegram_post_url(self, message_id: Optional[str]) -> Optional[str]:
        if not message_id:
            return None

        username = Config.TELEGRAM_CHANNEL_USERNAME.replace("@", "").strip()
        if not username:
            return None

        return f"https://t.me/{username}/{message_id}"