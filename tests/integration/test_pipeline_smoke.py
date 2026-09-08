import copy
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from src.core.config import Config
from src.factory.state_service import StateService
import src.main


FIXED_NEWS = {
    "title": "Smoke test AI news",
    "url": "https://example.com/smoke",
    "source": "Hacker News",
    "age_hours": 1,
    "summary": "Smoke summary",
}

FIXED_PLAN = {
    "created_at": "2026-09-07T10:00:00",
    "mode": "growth",
    "platform": "telegram",
    "topic": "Smoke test topic: AI smoke",
    "format": "Секретный промпт",
    "news": {
        "source": "Hacker News",
        "url": "https://example.com/smoke",
        "age_hours": 1,
    },
    "product": {
        "id": "channel",
        "name": "Smoke Channel",
        "description": "Smoke description",
        "category": "Telegram Channel",
        "affiliate_link": "https://t.me/smoke",
        "free_trial": False,
        "status": "active",
    },
    "language": "ru",
    "cta": "Подписаться на канал",
    "cta_link": "https://t.me/smoke",
    "is_affiliate": False,
}


class _DummyLogger:
    """Минимальная заглушка логгера, чтобы тест не писал в data/logs."""

    def step(self, *args, **kwargs): pass
    def success(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass
    def skip(self, *args, **kwargs): pass
    def debug(self, *args, **kwargs): pass
    def divider(self, *args, **kwargs): pass
    def header(self, *args, **kwargs): pass
    def summary(self, *args, **kwargs): pass
    def elapsed(self): return "0.0s"


class TestPipelineSmoke(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "factory.db")
        self.publish_calls = []

        def fake_publish(editor_result, image_path=None):
            self.publish_calls.append(1)
            return {
                "success": True,
                "platform": "telegram",
                "message_id": 777,
                "channel": "-100smoke",
                "final_text": editor_result.get("final_text", ""),
                "has_image": False,
                "plan": editor_result.get("plan", {}),
                "length": editor_result.get("length", 0),
                "ai_source": editor_result.get("ai_source", "test"),
            }

        self._patchers = [
            mock.patch.object(Config, "DATABASE_PATH", str(self.db_path)),
            mock.patch.object(
                Config,
                "validate",
                return_value={"valid": True, "issues": [], "ai_available": True, "missing": []},
            ),
            mock.patch("src.main.get_logger", return_value=_DummyLogger()),
            mock.patch("random.random", return_value=0.9),
            mock.patch("src.main.get_top_ai_news", return_value=[copy.deepcopy(FIXED_NEWS)]),
            mock.patch("src.main.get_fallback_topic", return_value=copy.deepcopy(FIXED_NEWS)),
            mock.patch(
                "src.main.create_content_plan",
                side_effect=lambda news_item=None: copy.deepcopy(FIXED_PLAN),
            ),
            mock.patch(
                "src.main.write_post",
                side_effect=lambda plan: {
                    "plan": plan,
                    "draft_text": "Черновик смоук-поста без запрещённых маркеров и достаточно длинный.",
                    "ai_source": "test-ai",
                    "format": plan.get("format"),
                    "mode": "growth",
                },
            ),
            mock.patch(
                "src.main.edit_post",
                side_effect=lambda cw: {
                    "plan": cw["plan"],
                    "final_text": "Финальный текст поста для смоук-теста.",
                    "ai_source": cw["ai_source"],
                    "length": 44,
                    "issues": [],
                    "ready": True,
                    "mode": "growth",
                },
            ),
            mock.patch("src.main.create_image_for_post", return_value=None),
            mock.patch("src.main.publish_post", side_effect=fake_publish),
            mock.patch("src.main.is_twitter_configured", return_value=False),
            mock.patch(
                "src.agents.twitter_writer.write_twitter_post",
                return_value={
                    "success": True,
                    "tweet_text": "смоук твит",
                    "tweet_length": 10,
                    "twitter_format": "Hook",
                    "cta_link": "https://t.me/smoke",
                    "using_affiliate_link": False,
                    "ai_source": "test-ai",
                },
            ),
            mock.patch("src.main.is_vk_configured", return_value=False),
            mock.patch("src.main.is_pinterest_configured", return_value=False),
            mock.patch(
                "src.integrations.telegram_admin.send_admin_notification",
                return_value={"success": True},
            ),
            mock.patch("src.main.log_publication", return_value={}),
        ]
        for patcher in self._patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()
        self.tmp_dir.cleanup()

    def _query(self, sql: str):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_full_path_and_rerun_protection(self) -> None:
        result_1 = src.main.run_pipeline()

        self.assertTrue(result_1["success"])
        self.assertEqual(len(self.publish_calls), 1)

        runs = self._query("SELECT status FROM pipeline_runs")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0][0], "COMPLETED")

        contents = self._query("SELECT status FROM content_items")
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0][0], "PUBLISHED")

        pubs = self._query(
            "SELECT status, external_post_id, attempt_count FROM publications"
        )
        self.assertEqual(len(pubs), 1)
        self.assertEqual(pubs[0][0], "PUBLISHED")
        self.assertEqual(pubs[0][1], "777")
        self.assertEqual(pubs[0][2], 1)

        result_2 = src.main.run_pipeline()

        self.assertTrue(result_2["success"])
        self.assertTrue(result_2.get("already_published"))
        self.assertEqual(len(self.publish_calls), 1)

        self.assertEqual(self._query("SELECT COUNT(*) FROM content_items")[0][0], 1)
        self.assertEqual(self._query("SELECT COUNT(*) FROM publications")[0][0], 1)

    def test_external_run_id_dedup(self) -> None:
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "424242",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        with mock.patch.dict(os.environ, env):
            result_1 = src.main.run_pipeline()
            self.assertTrue(result_1["success"])
            self.assertEqual(len(self.publish_calls), 1)

            result_2 = src.main.run_pipeline()
            self.assertTrue(result_2.get("duplicate_run"))
            self.assertEqual(len(self.publish_calls), 1)

        self.assertEqual(self._query("SELECT COUNT(*) FROM pipeline_runs")[0][0], 1)

    def test_interrupted_attempt_goes_manual_review(self) -> None:
        state = StateService(
            database_path=self.db_path,
            timezone_name="Europe/Kyiv",
        )
        content, _ = state.get_or_create_content_from_plan(copy.deepcopy(FIXED_PLAN))
        publication, _ = state.get_or_create_publication(content.content_id, "telegram")
        state.begin_publication(publication.publication_id)

        result = src.main.run_pipeline()

        self.assertFalse(result["success"])
        self.assertEqual(result.get("error"), "manual_review")
        self.assertEqual(len(self.publish_calls), 0)

        pubs = self._query("SELECT status FROM publications")
        self.assertEqual(len(pubs), 1)
        self.assertEqual(pubs[0][0], "MANUAL_REVIEW")

        runs = self._query("SELECT status FROM pipeline_runs")
        self.assertEqual(runs[-1][0], "FAILED")


if __name__ == "__main__":
    unittest.main()