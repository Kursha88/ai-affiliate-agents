#!/usr/bin/env python3
"""Read-only SQLite integrity check for the pipeline state database.

Used by the GitHub Actions persistence step BEFORE data/factory.db is
staged or committed, so that a corrupt database can never enter Git
history.

Guarantees:
    - opens an existing DB strictly read-only (URI ?mode=ro);
    - never repairs, writes, or otherwise modifies the database;
    - standard library only.

Exit codes:
    0  quick_check returned 'ok', or the DB file does not exist
       (fresh runner / pipeline never created it);
    1  quick_check found corruption, or the DB could not be
       opened / read / checked for any other reason;
    2  usage error (wrong number of arguments).
"""

from __future__ import annotations

import os
import sqlite3
import sys


def _readonly_uri(db_path: str) -> str:
    """Build a SQLite URI that forces read-only access."""
    # Normalize Windows separators for URI form; forward slashes are
    # valid in SQLite URI paths on all platforms.
    uri_path = db_path.replace("\\", "/")
    return f"file:{uri_path}?mode=ro"


def check_integrity(db_path: str) -> int:
    if not os.path.exists(db_path):
        print(f"INTEGRITY SKIP: database file not found: {db_path}")
        print("Nothing to check this run (fresh runner or DB not yet created).")
        return 0

    try:
        conn = sqlite3.connect(_readonly_uri(db_path), uri=True)
    except (sqlite3.Error, OSError) as exc:
        print(f"INTEGRITY FAIL: cannot open database read-only: {db_path}")
        print(f"Reason: {exc}")
        return 1

    try:
        rows = conn.execute("PRAGMA quick_check").fetchall()
    except (sqlite3.DatabaseError, OSError) as exc:
        print(f"INTEGRITY FAIL: SQLite could not read/check database: {db_path}")
        print(f"Reason: {exc}")
        return 1
    finally:
        conn.close()

    first = rows[0][0] if rows else None

    if first == "ok" and len(rows) == 1:
        print(f"INTEGRITY OK: {db_path}")
        return 0

    print(f"INTEGRITY FAIL: database corruption detected: {db_path}")
    for row in rows[:10]:
        print(f"quick_check: {row[0]}")
    if len(rows) > 10:
        print(f"... and {len(rows) - 10} more quick_check issue(s)")
    return 1


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python scripts/check_db_integrity.py <database-path>")
        return 2
    return check_integrity(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
