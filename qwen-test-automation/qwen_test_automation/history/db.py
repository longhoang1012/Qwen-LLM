from __future__ import annotations

import json
import sqlite3

from qwen_test_automation.models import TestCase

_SCHEMA = """
CREATE TABLE IF NOT EXISTS testcases (
  id TEXT PRIMARY KEY, feature TEXT, precondition TEXT,
  steps_json TEXT, expected_result TEXT, platform TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  testcase_id TEXT NOT NULL REFERENCES testcases(id),
  status TEXT NOT NULL CHECK(status IN ('pass','fail','pending_claude_review','blocked')),
  failure_type TEXT CHECK(failure_type IN ('locator','assertion') OR failure_type IS NULL),
  message TEXT, started_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def insert_testcase(conn: sqlite3.Connection, testcase: TestCase) -> None:
    conn.execute(
        "INSERT INTO testcases (id, feature, precondition, steps_json, expected_result, platform) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            testcase.id,
            testcase.feature,
            testcase.precondition,
            json.dumps(testcase.steps),
            testcase.expected_result,
            testcase.platform,
        ),
    )
    conn.commit()


def get_testcase(conn: sqlite3.Connection, testcase_id: str) -> TestCase | None:
    row = conn.execute(
        "SELECT id, feature, precondition, steps_json, expected_result, platform "
        "FROM testcases WHERE id = ?",
        (testcase_id,),
    ).fetchone()
    if row is None:
        return None
    return TestCase(
        id=row["id"],
        feature=row["feature"],
        precondition=row["precondition"],
        steps=json.loads(row["steps_json"]),
        expected_result=row["expected_result"],
        platform=row["platform"],
    )


def record_run(
    conn: sqlite3.Connection,
    testcase_id: str,
    status: str,
    failure_type: str | None,
    message: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO runs (testcase_id, status, failure_type, message) VALUES (?, ?, ?, ?)",
        (testcase_id, status, failure_type, message),
    )
    conn.commit()
    return cur.lastrowid


def get_pending_review(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT r.*, t.feature AS testcase_feature, t.platform AS testcase_platform
        FROM runs r
        JOIN testcases t ON t.id = r.testcase_id
        WHERE r.id IN (SELECT MAX(id) FROM runs GROUP BY testcase_id)
          AND r.status = 'pending_claude_review'
        ORDER BY r.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]
