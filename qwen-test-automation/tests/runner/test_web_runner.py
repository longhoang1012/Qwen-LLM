import os

import pytest

from qwen_test_automation.models import TestCase
from qwen_test_automation.history.db import init_db, get_pending_review
from qwen_test_automation.runner.safety_gate import HostNotAllowedError
from qwen_test_automation.runner.script_store import save_script, load_script
from qwen_test_automation.runner.script_safety import ScriptCompileError
from qwen_test_automation.runner.web_runner import ensure_script_generated, run_web_testcase


class FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text
        self.called = False

    def generate(self, model, prompt, images=None):
        self.called = True
        return self.response_text


def make_testcase():
    return TestCase(
        id="TC-001", feature="Login", precondition="Account exists",
        steps=["Open login page", "Login"], expected_result="Dashboard shown",
        platform="WTS",
    )


ALLOWED = {"uat.example.internal"}
URL = "https://uat.example.internal"


# --- ensure_script_generated (phase 2: generate + review window) ---

def test_ensure_script_generated_generates_and_saves_when_missing(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = FakeClient("import sys\nsys.exit(0)\n")
    path = ensure_script_generated(make_testcase(), client, "m", scripts_dir, ALLOWED)
    assert client.called
    assert load_script("TC-001", scripts_dir) == "import sys\nsys.exit(0)"
    assert os.path.exists(path)


def test_ensure_script_generated_strips_markdown_fence(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = FakeClient("```python\nimport sys\nsys.exit(0)\n```")
    ensure_script_generated(make_testcase(), client, "m", scripts_dir, ALLOWED)
    assert load_script("TC-001", scripts_dir) == "import sys\nsys.exit(0)"


def test_ensure_script_generated_reuses_existing_without_regenerating(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    save_script("TC-001", "import sys\nsys.exit(0)\n", scripts_dir)
    client = FakeClient("not valid python at all")
    ensure_script_generated(make_testcase(), client, "m", scripts_dir, ALLOWED)
    assert not client.called


def test_ensure_script_generated_raises_on_invalid_syntax(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = FakeClient("def f(:\n")
    with pytest.raises(ScriptCompileError):
        ensure_script_generated(make_testcase(), client, "m", scripts_dir, ALLOWED)
    assert load_script("TC-001", scripts_dir) is None


def test_ensure_script_generated_raises_on_disallowed_host(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = FakeClient("page.goto('https://prod.evil.com/login')\n")
    with pytest.raises(HostNotAllowedError):
        ensure_script_generated(make_testcase(), client, "m", scripts_dir, ALLOWED)
    assert load_script("TC-001", scripts_dir) is None


# --- run_web_testcase (phase 3: run an existing script, no Qwen calls) ---

def test_run_web_testcase_refuses_disallowed_host(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    with pytest.raises(HostNotAllowedError):
        run_web_testcase(
            make_testcase(), "https://prod.example.com",
            allowed_hosts=set(), scripts_dir=str(tmp_path / "scripts"), conn=conn,
        )


def test_run_web_testcase_marks_pending_review_when_no_script_exists(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    status = run_web_testcase(
        make_testcase(), URL,
        allowed_hosts=ALLOWED, scripts_dir=str(tmp_path / "scripts"), conn=conn,
    )
    assert status == "pending_claude_review"
    pending = get_pending_review(conn)
    assert len(pending) == 1
    assert pending[0]["testcase_id"] == "TC-001"


def test_run_web_testcase_passes(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    save_script("TC-001", "import sys\nsys.exit(0)\n", scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    status = run_web_testcase(
        make_testcase(), URL,
        allowed_hosts=ALLOWED, scripts_dir=scripts_dir, conn=conn,
    )
    assert status == "pass"


def test_run_web_testcase_blocks_script_referencing_disallowed_host(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    save_script("TC-001", "page.goto('https://prod.evil.com/login')\nimport sys\nsys.exit(0)\n", scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    status = run_web_testcase(
        make_testcase(), URL,
        allowed_hosts=ALLOWED, scripts_dir=scripts_dir, conn=conn,
    )
    assert status == "blocked"


def test_run_web_testcase_passes_base_url_and_credentials_as_env_vars(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    script = (
        "import os, sys\n"
        "ok = (os.environ.get('QWEN_TEST_BASE_URL') == 'https://uat.example.internal'\n"
        "      and os.environ.get('QWEN_TEST_ACCOUNT') == '0000000001'\n"
        "      and os.environ.get('QWEN_TEST_PASSWORD') == 'x'\n"
        "      and os.environ.get('QWEN_TEST_OTP') == '000000')\n"
        "sys.exit(0 if ok else 1)\n"
    )
    save_script("TC-001", script, scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    credentials = {"0000000001": {"password": "x", "default_otp": "000000"}}
    status = run_web_testcase(
        make_testcase(), URL,
        allowed_hosts=ALLOWED, scripts_dir=scripts_dir, conn=conn,
        credentials=credentials, account="0000000001",
    )
    assert status == "pass"


def test_run_web_testcase_assertion_failure_retries_exactly_once_then_fails(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    counter_file = str(tmp_path / "counter.txt")
    script = (
        "import sys\n"
        f"path = {counter_file!r}\n"
        "try:\n"
        "    with open(path) as f:\n"
        "        n = int(f.read())\n"
        "except FileNotFoundError:\n"
        "    n = 0\n"
        "n += 1\n"
        "with open(path, 'w') as f:\n"
        "    f.write(str(n))\n"
        "assert False, 'boom'\n"
    )
    save_script("TC-001", script, scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    status = run_web_testcase(
        make_testcase(), URL,
        allowed_hosts=ALLOWED, scripts_dir=scripts_dir, conn=conn,
    )
    assert status == "fail"
    with open(counter_file) as f:
        assert f.read() == "2"  # exactly one retry: ran twice total
    assert get_pending_review(conn) == []


def test_run_web_testcase_assertion_failure_passes_on_retry(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    counter_file = str(tmp_path / "counter.txt")
    script = (
        "import sys\n"
        f"path = {counter_file!r}\n"
        "try:\n"
        "    with open(path) as f:\n"
        "        n = int(f.read())\n"
        "except FileNotFoundError:\n"
        "    n = 0\n"
        "n += 1\n"
        "with open(path, 'w') as f:\n"
        "    f.write(str(n))\n"
        "assert n > 1, 'boom'\n"
    )
    save_script("TC-001", script, scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    status = run_web_testcase(
        make_testcase(), URL,
        allowed_hosts=ALLOWED, scripts_dir=scripts_dir, conn=conn,
    )
    assert status == "pass"


def test_run_web_testcase_retry_reclassified_as_locator_is_pending_review(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    counter_file = str(tmp_path / "counter.txt")
    script = (
        "import sys\n"
        f"path = {counter_file!r}\n"
        "try:\n"
        "    with open(path) as f:\n"
        "        n = int(f.read())\n"
        "except FileNotFoundError:\n"
        "    n = 0\n"
        "n += 1\n"
        "with open(path, 'w') as f:\n"
        "    f.write(str(n))\n"
        "if n == 1:\n"
        "    assert False, 'boom'\n"
        "else:\n"
        "    raise TimeoutError('Timeout 5000ms exceeded')\n"
    )
    save_script("TC-001", script, scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    status = run_web_testcase(
        make_testcase(), URL,
        allowed_hosts=ALLOWED, scripts_dir=scripts_dir, conn=conn,
    )
    assert status == "pending_claude_review"


def test_run_web_testcase_locator_failure_marks_pending_review_without_retry(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    counter_file = str(tmp_path / "counter.txt")
    script = (
        "import sys\n"
        f"path = {counter_file!r}\n"
        "try:\n"
        "    with open(path) as f:\n"
        "        n = int(f.read())\n"
        "except FileNotFoundError:\n"
        "    n = 0\n"
        "n += 1\n"
        "with open(path, 'w') as f:\n"
        "    f.write(str(n))\n"
        "raise TimeoutError('Timeout 30000ms exceeded')\n"
    )
    save_script("TC-001", script, scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    status = run_web_testcase(
        make_testcase(), URL,
        allowed_hosts=ALLOWED, scripts_dir=scripts_dir, conn=conn,
    )
    assert status == "pending_claude_review"
    with open(counter_file) as f:
        assert f.read() == "1"  # no retry for a locator-type failure


def test_run_web_testcase_timeout_is_recorded_as_pending_review(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    save_script("TC-001", "import time\ntime.sleep(5)\n", scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    status = run_web_testcase(
        make_testcase(), URL,
        allowed_hosts=ALLOWED, scripts_dir=scripts_dir, conn=conn,
        timeout=1,
    )
    assert status == "pending_claude_review"
    assert len(get_pending_review(conn)) == 1


def test_run_web_testcase_redacts_credentials_from_stored_message(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    script = (
        "import os, sys\n"
        "print('leaked password: ' + os.environ['QWEN_TEST_PASSWORD'], file=sys.stderr)\n"
        "raise TimeoutError('Timeout 1000ms exceeded')\n"
    )
    save_script("TC-001", script, scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    credentials = {"0000000001": {"password": "SuperSecret123", "default_otp": "000000"}}
    run_web_testcase(
        make_testcase(), URL,
        allowed_hosts=ALLOWED, scripts_dir=scripts_dir, conn=conn,
        credentials=credentials, account="0000000001",
    )
    pending = get_pending_review(conn)
    assert "SuperSecret123" not in pending[0]["message"]
