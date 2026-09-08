import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "check_db_integrity.py"


class TestDbIntegrityCheck(unittest.TestCase):
    """
    Safety contract for scripts/check_db_integrity.py.

    All cases run against temporary paths only. The production
    data/factory.db is never passed to the script here.
    """

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def _run(self, db_path: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), db_path],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )

    def test_valid_temp_sqlite_db_exits_zero(self) -> None:
        db_path = os.path.join(self.tmp_dir.name, "valid.db")
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
            conn.execute("INSERT INTO t (v) VALUES ('hello')")
            conn.commit()
        finally:
            conn.close()

        result = self._run(db_path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("INTEGRITY OK", result.stdout)

    def test_missing_db_path_exits_zero(self) -> None:
        db_path = os.path.join(self.tmp_dir.name, "does_not_exist.db")

        result = self._run(db_path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("INTEGRITY SKIP", result.stdout)

    def test_garbage_file_exits_non_zero(self) -> None:
        db_path = os.path.join(self.tmp_dir.name, "garbage.db")
        with open(db_path, "wb") as f:
            f.write(b"\x00\x01\x02NOT_A_SQLITE_FILE" + bytes(range(256)) * 4)

        result = self._run(db_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INTEGRITY FAIL", result.stdout)

    def test_state_service_created_db_exits_zero(self) -> None:
        from src.factory.state_service import StateService

        db_path = os.path.join(self.tmp_dir.name, "state.db")
        state = StateService(
            database_path=db_path,
            timezone_name="Europe/Kyiv",
        )
        # Exercise the storage layer so the DB contains real schema + rows.
        run, _ = state.start_pipeline_run(mode="growth", trigger="test")
        state.fail_run(run.run_id, "TEST", "test failure")

        result = self._run(db_path)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("INTEGRITY OK", result.stdout)

    def test_missing_argument_exits_non_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
