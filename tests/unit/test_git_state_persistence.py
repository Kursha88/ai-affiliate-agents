import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GITATTRIBUTES = PROJECT_ROOT / ".gitattributes"
GITIGNORE = PROJECT_ROOT / ".gitignore"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "scheduler.yml"


class TestGitStatePersistence(unittest.TestCase):
    """
    Regression tests for the temporary Git-based persistence safety contract.

    These tests assert safety invariants only - not exact formatting of the
    workflow, so small cosmetic edits do not break them.
    """

    def setUp(self) -> None:
        self.assertTrue(
            GITATTRIBUTES.exists(),
            ".gitattributes must exist (Step 1 contract)",
        )
        self.assertTrue(
            GITIGNORE.exists(),
            ".gitignore must exist",
        )
        self.assertTrue(
            WORKFLOW.exists(),
            "scheduler.yml must exist",
        )
        self.gitattributes = GITATTRIBUTES.read_text(encoding="utf-8")
        self.gitignore = GITIGNORE.read_text(encoding="utf-8")
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    # ── .gitattributes: binary handling, no auto-merge driver ──

    def test_gitattributes_marks_factory_db_binary(self) -> None:
        self.assertIn(
            "data/factory.db binary",
            self.gitattributes,
            "data/factory.db must be marked binary (-text -diff -merge)",
        )

    def test_gitattributes_does_not_configure_ours_merge_driver(self) -> None:
        self.assertNotIn(
            "merge.ours",
            self.gitattributes,
            "automatic 'ours' merge driver is forbidden for the state DB",
        )

    # ── .gitignore: SQLite sidecars ignored, DB itself not ignored ──

    def test_gitignore_ignores_sqlite_sidecar_files(self) -> None:
        for sidecar in (
            "data/factory.db-journal",
            "data/factory.db-wal",
            "data/factory.db-shm",
        ):
            with self.subTest(sidecar=sidecar):
                self.assertIn(
                    sidecar,
                    self.gitignore,
                    f"{sidecar} must be gitignored",
                )

    def test_gitignore_does_not_ignore_the_database_itself(self) -> None:
        # The exact path 'data/factory.db' must not appear as an ignore rule.
        # Sidecar entries (data/factory.db-journal etc.) are fine.
        for line in self.gitignore.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            self.assertNotEqual(
                stripped,
                "data/factory.db",
                "data/factory.db itself must NOT be gitignored",
            )

    # ── scheduler.yml: preserved safety properties ──

    def test_persistence_step_retains_if_always(self) -> None:
        self.assertIn(
            "if: always()",
            self.workflow,
            "persistence step must keep if: always() so failed runs still persist state",
        )

    def test_workflow_retains_concurrency_group(self) -> None:
        self.assertIn(
            "ai-affiliate-pipeline",
            self.workflow,
            "concurrency group must be preserved",
        )
        self.assertIn(
            "cancel-in-progress: false",
            self.workflow,
            "cancel-in-progress: false must be preserved",
        )

    def test_persistence_logic_invokes_integrity_gate(self) -> None:
        self.assertIn(
            "python scripts/check_db_integrity.py data/factory.db",
            self.workflow,
            "persistence step must run the integrity gate before staging the DB",
        )

    def test_persistence_logic_contains_no_unsafe_operations(self) -> None:
        forbidden = [
            "|| true",
            "reset --hard",
            "--force",
            "--force-with-lease",
            "checkout --ours",
            "checkout --theirs",
            "merge.ours",
        ]
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(
                    token,
                    self.workflow,
                    f"forbidden unsafe operation in persistence logic: {token}",
                )

    # ── Legacy persistence files: not force-added, not unignored ──

    def test_legacy_files_are_not_force_added_or_unignored(self) -> None:
        # Match actual force-add invocations, not unrelated tokens like
        # the POSIX file test '[ -f "$f" ]' used in the staging helper.
        for force_add in ("git add -f", "git add --force"):
            with self.subTest(force_add=force_add):
                self.assertNotIn(
                    force_add,
                    self.workflow,
                    f"workflow must not force-add ignored files: {force_add}",
                )
        # The legacy files must still be listed as ignored in .gitignore.
        self.assertIn(
            "data/published_posts.csv",
            self.gitignore,
            "data/published_posts.csv must remain gitignored (unchanged scope)",
        )
        self.assertIn(
            "data/topic_history.json",
            self.gitignore,
            "data/topic_history.json must remain gitignored (unchanged scope)",
        )


if __name__ == "__main__":
    unittest.main()
