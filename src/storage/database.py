from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

SCHEMA_VERSION = 1


class Database:
    """
    SQLite database layer.

    - не использует глобальный connection;
    - включает foreign keys;
    - использует transactions через context manager;
    - автоматически создаёт схему.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    version INTEGER NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )

            row = conn.execute("SELECT MAX(version) FROM schema_meta").fetchone()
            current_version = row[0] if row else None

            if current_version is None:
                conn.execute(
                    "INSERT INTO schema_meta (version, applied_at) VALUES (?, ?)",
                    (
                        SCHEMA_VERSION,
                        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    ),
                )
            elif current_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported database schema version: {current_version}. "
                    f"Current application supports version {SCHEMA_VERSION}."
                )

            # Future migrations should be added here incrementally.
            # Do not drop existing data.

            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    business_date TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    trigger_external_id TEXT,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    duration_seconds INTEGER,
                    schema_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status
                    ON pipeline_runs(status);

                CREATE INDEX IF NOT EXISTS idx_pipeline_runs_business_date
                    ON pipeline_runs(business_date);

                CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at
                    ON pipeline_runs(started_at);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_pipeline_runs_trigger_external_id
                    ON pipeline_runs(trigger_external_id)
                    WHERE trigger_external_id IS NOT NULL;

                CREATE TABLE IF NOT EXISTS content_items (
                    content_id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    content_cluster TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    normalized_topic TEXT NOT NULL,
                    format TEXT NOT NULL,
                    language TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    source_item_id TEXT,
                    source_url TEXT,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    content_hash TEXT NOT NULL,
                    business_date TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_content_items_status
                    ON content_items(status);

                CREATE INDEX IF NOT EXISTS idx_content_items_content_cluster
                    ON content_items(content_cluster);

                CREATE INDEX IF NOT EXISTS idx_content_items_business_date
                    ON content_items(business_date);

                CREATE INDEX IF NOT EXISTS idx_content_items_created_at
                    ON content_items(created_at);

                CREATE TABLE IF NOT EXISTS publications (
                    publication_id TEXT PRIMARY KEY,
                    content_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    status TEXT NOT NULL,
                    external_post_id TEXT,
                    post_url TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at TEXT,
                    scheduled_at TEXT,
                    published_at TEXT,
                    business_date TEXT NOT NULL,
                    slot_number INTEGER,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CONSTRAINT fk_publications_content_id
                        FOREIGN KEY (content_id)
                        REFERENCES content_items(content_id),
                    CONSTRAINT uq_publications_content_platform
                        UNIQUE (content_id, platform)
                );

                CREATE INDEX IF NOT EXISTS idx_publications_content_id
                    ON publications(content_id);

                CREATE INDEX IF NOT EXISTS idx_publications_platform
                    ON publications(platform);

                CREATE INDEX IF NOT EXISTS idx_publications_status
                    ON publications(status);

                CREATE INDEX IF NOT EXISTS idx_publications_business_date
                    ON publications(business_date);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_publications_platform_external_post_id
                    ON publications(platform, external_post_id)
                    WHERE external_post_id IS NOT NULL;
                """
            )