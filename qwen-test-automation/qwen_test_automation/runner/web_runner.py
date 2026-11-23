from qwen_test_automation.llm.script_generator import generate_script
from qwen_test_automation.history.db import insert_testcase, get_testcase, record_run
from qwen_test_automation.runner.safety_gate import assert_host_allowed, HostNotAllowedError
from qwen_test_automation.runner.script_store import load_script, save_script, script_path_for
from qwen_test_automation.runner.playwright_executor import run_script, ExecutionTimeoutError
from qwen_test_automation.runner.failure_triage import classify_failure
from qwen_test_automation.runner.script_safety import (
    strip_code_fence,
    assert_script_compiles,
    assert_script_hosts_allowed,
)

_REDACTED = "***"


def ensure_script_generated(testcase, client, model, scripts_dir, allowed_hosts):
    """Phase 2 (spec §6 step 2): generate and save a script for review.

    Never executes anything. Returns the existing script's path without
    calling Qwen if one is already saved — regenerating a reviewed script
    is a deliberate, separate action, not an implicit side effect of
    running it.
    """
    existing = load_script(testcase.id, scripts_dir)
    if existing is not None:
        return script_path_for(testcase.id, scripts_dir)

    raw = generate_script(testcase, client=client, model=model)
    source = strip_code_fence(raw)
    assert_script_compiles(source)
    assert_script_hosts_allowed(source, allowed_hosts)
    return save_script(testcase.id, source, scripts_dir)


def _redact(text, credentials, account):
    if not (account and credentials and account in credentials):
        return text
    acc = credentials[account]
    for value in (acc.get("password"), acc.get("default_otp")):
        if value:
            text = text.replace(value, _REDACTED)
    return text


def run_web_testcase(
    testcase, url, allowed_hosts, scripts_dir, conn,
    credentials=None, account=None, timeout=60,
):
    """Phase 3 (spec §6 step 3): run an already-reviewed script (B), or
    mark the testcase for Claude fallback (C) when none exists yet.

    Never calls Qwen — use `ensure_script_generated` as a separate step
    first, so a human has a window to review the generated script before
    anything runs it.
    """
    assert_host_allowed(url, allowed_hosts)

    if get_testcase(conn, testcase.id) is None:
        insert_testcase(conn, testcase)

    source = load_script(testcase.id, scripts_dir)
    if source is None:
        record_run(
            conn, testcase.id, "pending_claude_review", "locator",
            "no script generated yet for this testcase",
        )
        return "pending_claude_review"

    try:
        assert_script_hosts_allowed(source, allowed_hosts)
    except HostNotAllowedError as e:
        record_run(conn, testcase.id, "blocked", None, str(e))
        return "blocked"

    path = script_path_for(testcase.id, scripts_dir)

    env = {"QWEN_TEST_BASE_URL": url}
    if account and credentials:
        acc = credentials[account]
        env.update({
            "QWEN_TEST_ACCOUNT": account,
            "QWEN_TEST_PASSWORD": acc["password"],
            "QWEN_TEST_OTP": acc["default_otp"],
        })

    try:
        result = run_script(path, env=env, timeout=timeout)
    except ExecutionTimeoutError as e:
        record_run(
            conn, testcase.id, "pending_claude_review", "locator",
            _redact(str(e), credentials, account),
        )
        return "pending_claude_review"

    if result.returncode == 0:
        record_run(conn, testcase.id, "pass", None, "")
        return "pass"

    failure_type = classify_failure(result.stderr)
    if failure_type != "assertion":
        record_run(
            conn, testcase.id, "pending_claude_review", "locator",
            _redact(result.stderr[-500:], credentials, account),
        )
        return "pending_claude_review"

    try:
        retry = run_script(path, env=env, timeout=timeout)
    except ExecutionTimeoutError as e:
        record_run(
            conn, testcase.id, "pending_claude_review", "locator",
            _redact(str(e), credentials, account),
        )
        return "pending_claude_review"

    if retry.returncode == 0:
        record_run(conn, testcase.id, "pass", None, "")
        return "pass"

    retry_failure_type = classify_failure(retry.stderr)
    message = _redact(retry.stderr[-500:], credentials, account)
    if retry_failure_type == "assertion":
        record_run(conn, testcase.id, "fail", "assertion", message)
        return "fail"

    record_run(conn, testcase.id, "pending_claude_review", "locator", message)
    return "pending_claude_review"
