import os
import sqlite3
import tempfile
import unittest

from src.domain.models import PublicationStatus, RunStatus
from src.factory.state_service import StateService


class TestStorage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "factory.db")

        self.state = StateService(
            database_path=self.db_path,
            timezone_name="Europe/Kyiv",
        )

        self.plan = {
            "topic": "Test AI Topic",
            "format": "Секретный промпт",
            "language": "ru",
            "mode": "growth",
            "news": {
                "source": "Hacker News",
                "url": "https://example.com/news",
                "age_hours": 2,
            },
            "product": {
                "id": "channel",
                "name": "AI Channel",
                "description": "Telegram channel",
                "affiliate_link": "https://t.me/test",
            },
            "cta": "Подписаться",
            "cta_link": "https://t.me/test",
        }

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_database_tables_exist(self) -> None:
        with self.state.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()

        tables = {row["name"] for row in rows}

        self.assertIn("pipeline_runs", tables)
        self.assertIn("content_items", tables)
        self.assertIn("publications", tables)
        self.assertIn("schema_meta", tables)

    def test_foreign_key_publication_requires_content(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            with self.state.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO publications (
                        publication_id,
                        content_id,
                        platform,
                        status,
                        idempotency_key,
                        attempt_count,
                        business_date,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "pub_nonexistent",
                        "content_nonexistent",
                        "telegram",
                        PublicationStatus.PENDING,
                        "idem_nonexistent",
                        0,
                        "2026-09-07",
                        "2026-09-07T00:00:00Z",
                        "2026-09-07T00:00:00Z",
                    ),
                )

    def test_content_idempotency(self) -> None:
        content_1, created_1 = self.state.get_or_create_content_from_plan(
            self.plan,
            business_date="2026-09-07",
        )
        content_2, created_2 = self.state.get_or_create_content_from_plan(
            self.plan,
            business_date="2026-09-07",
        )

        self.assertTrue(created_1)
        self.assertFalse(created_2)
        self.assertEqual(content_1.content_id, content_2.content_id)

    def test_publication_idempotency(self) -> None:
        content, _ = self.state.get_or_create_content_from_plan(
            self.plan,
            business_date="2026-09-07",
        )

        pub_1, created_1 = self.state.get_or_create_publication(
            content_id=content.content_id,
            platform="telegram",
            business_date="2026-09-07",
        )

        pub_2, created_2 = self.state.get_or_create_publication(
            content_id=content.content_id,
            platform="telegram",
            business_date="2026-09-07",
        )

        self.assertTrue(created_1)
        self.assertFalse(created_2)
        self.assertEqual(pub_1.publication_id, pub_2.publication_id)

    def test_published_protection(self) -> None:
        content, _ = self.state.get_or_create_content_from_plan(
            self.plan,
            business_date="2026-09-07",
        )

        publication, _ = self.state.get_or_create_publication(
            content_id=content.content_id,
            platform="telegram",
            business_date="2026-09-07",
        )

        self.state.begin_publication(publication.publication_id)
        self.state.mark_publication_published(
            publication_id=publication.publication_id,
            external_post_id="123",
            post_url="https://t.me/test/123",
        )

        publication = self.state.publications.get(publication.publication_id)
        allowed, reason = self.state.guard_publication(publication)

        self.assertFalse(allowed)
        self.assertEqual(reason, "already_published")

    def test_unknown_interrupted_attempt_goes_to_manual_review(self) -> None:
        content, _ = self.state.get_or_create_content_from_plan(
            self.plan,
            business_date="2026-09-07",
        )

        publication, _ = self.state.get_or_create_publication(
            content_id=content.content_id,
            platform="telegram",
            business_date="2026-09-07",
        )

        self.state.begin_publication(publication.publication_id)

        allowed, reason = self.state.guard_publication(publication)

        self.assertFalse(allowed)
        self.assertEqual(reason, "manual_review")

        publication = self.state.publications.get(publication.publication_id)
        self.assertEqual(publication.status, PublicationStatus.MANUAL_REVIEW)

    def test_pipeline_run_lifecycle(self) -> None:
        run, created = self.state.start_pipeline_run(
            mode="growth",
            trigger="test",
            trigger_external_id=None,
        )

        self.assertTrue(created)
        self.assertEqual(run.status, RunStatus.RUNNING)

        self.state.complete_run(run.run_id)
        run = self.state.runs.get(run.run_id)
        self.assertEqual(run.status, RunStatus.COMPLETED)

        run_2, created_2 = self.state.start_pipeline_run(
            mode="growth",
            trigger="test",
            trigger_external_id=None,
        )

        self.assertTrue(created_2)
        self.state.fail_run(run_2.run_id, "TEST_ERROR", "Test failure")
        run_2 = self.state.runs.get(run_2.run_id)
        self.assertEqual(run_2.status, RunStatus.FAILED)


if __name__ == "__main__":
    unittest.main()