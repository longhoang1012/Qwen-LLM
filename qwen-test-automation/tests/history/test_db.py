from qwen_test_automation.models import TestCase
from qwen_test_automation.history.db import (
    init_db,
    insert_testcase,
    get_testcase,
    record_run,
    get_pending_review,
)


def make_testcase():
    return TestCase(
        id="TC-001", feature="Login", precondition="Account exists",
        steps=["Open app", "Login"], expected_result="Dashboard shown",
        platform="MTS-Android",
    )


def test_insert_and_get_testcase_round_trips(tmp_path):
    conn = init_db(str(tmp_path / "history.db"))
    tc = make_testcase()
    insert_testcase(conn, tc)
    assert get_testcase(conn, "TC-001") == tc


def test_get_testcase_missing_returns_none(tmp_path):
    conn = init_db(str(tmp_path / "history.db"))
    assert get_testcase(conn, "nope") is None


def test_record_run_and_get_pending_review(tmp_path):
    conn = init_db(str(tmp_path / "history.db"))
    insert_testcase(conn, make_testcase())
    run_id = record_run(conn, "TC-001", "pending_claude_review", "locator", "selector not found")
    assert isinstance(run_id, int)
    pending = get_pending_review(conn)
    assert len(pending) == 1
    assert pending[0]["testcase_id"] == "TC-001"
    assert pending[0]["failure_type"] == "locator"


def test_pending_review_excludes_testcase_whose_latest_run_is_resolved(tmp_path):
    conn = init_db(str(tmp_path / "history.db"))
    insert_testcase(conn, make_testcase())
    record_run(conn, "TC-001", "pending_claude_review", "locator", "selector not found")
    record_run(conn, "TC-001", "pass", None, "resolved by Claude")
    assert get_pending_review(conn) == []


def test_record_run_accepts_blocked_status(tmp_path):
    conn = init_db(str(tmp_path / "history.db"))
    insert_testcase(conn, make_testcase())
    run_id = record_run(conn, "TC-001", "blocked", None, "host not in allowlist")
    assert isinstance(run_id, int)
