# Qwen Automation Web Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a `TestCase` against WTS/MWTS safely and cheaply — load an
existing Playwright script or have Qwen generate one, execute it without
any AI in the loop, triage failures, and record the result — the
"testcase in, pass/fail on the browser out" half of the tool, completing
the Hybrid (approach C) architecture from the spec.

**Architecture:** `runner/safety_gate.py` refuses to run against any host
not in the allowlist, before anything else happens. `runner/script_store.py`
persists one generated script per testcase id. `runner/playwright_executor.py`
runs a script as a plain subprocess and captures its exit code/output —
the script itself is a standalone Python file (not a pytest test), so
running it needs nothing but the interpreter and whatever libraries it
imports. `runner/failure_triage.py` classifies a failure as
structural/locator (needs Claude) or business-logic/assertion (likely a
real bug, retried once). `runner/web_runner.py` wires all of this plus
Foundation's `history.db` into one call per testcase. A small, separate
first task hardens Foundation's `script_generator.py` prompt — it never
had a safety or contract or credential-handling instruction, and this
runner is its first real caller.

**Tech Stack:** Same Python venv as Foundation/Ingestion
(`qwen-test-automation/.venv`). No new third-party dependency — `subprocess`
and `urllib.parse` are stdlib. Running a *real* Playwright script needs
`playwright` (`pip install playwright && playwright install chromium`,
not required for this plan's own tests, which use plain Python scripts
to exercise the executor).

**Spec:** [docs/superpowers/specs/2026-11-20-local-qwen-automation-design.md](../specs/2026-11-20-local-qwen-automation-design.md)
(§4 anti-goals — safety gate, real-transaction rule; §6 — safety gate,
async fallback, failure triage, credential handling; §9 — WTS/MWTS host
and account semantics still unconfirmed, see Constraints)

## Global Constraints

- Script sinh ra cho giao dịch thật (đặt/sửa/huỷ lệnh, chuyển/rút tiền)
  phải dừng trước bước submit cuối, không tự bấm xác nhận — ngay cả trên
  host UAT đã xác nhận an toàn (spec §4).
- `runner` không được login/thao tác trên một host chưa nằm trong
  allowlist đã cấu hình — từ chối chạy ngay, không thử login (spec §6).
- Lỗi cấu trúc/locator (selector không tìm thấy, timeout, crash) → xếp
  vào hàng đợi cần Claude xác minh; lỗi assertion nghiệp vụ → retry đúng
  1 lần, vẫn fail thì báo thẳng là nghi vấn bug (spec §6).
- Credential (account/password/OTP) không bao giờ bị in ra log/stdout/
  stderr hay ghi vào history.db — chỉ được truyền cho script con qua
  biến môi trường của tiến trình con.
- URL/host thật của WTS/MWTS và ý nghĩa của 8 account test vẫn chưa được
  xác nhận (spec §9) — các task dưới đây dùng host/account do caller
  truyền vào tham số, không hard-code; việc chạy thật trên WTS/MWTS thật
  là bước xác minh thủ công sau khi có thông tin đó, không phải một phần
  của task nào ở đây.

## Review Focus

- Host không nằm trong allowlist vẫn bị cố gắng login/thao tác →
  `assert_host_allowed` phải raise ngay, không chạy script. (Task 2)
- Script thất bại với lỗi không khớp pattern nào đã biết (không rõ
  nguyên nhân) → phải mặc định xếp vào "cần Claude xác minh" (locator),
  không tự ý kết luận là bug. (Task 4)
- Script chạy quá lâu (treo, không bao giờ thoát) → phải timeout rõ
  ràng, không treo vô thời hạn. (Task 5)
- Lỗi assertion (nghi vấn bug nghiệp vụ) → phải retry đúng 1 lần trước
  khi kết luận fail, không fail ngay từ lần chạy đầu (giảm flaky).
  (Task 6)
- Chưa có script sẵn cho testcase → phải tự sinh qua Qwen, lưu lại, và
  **phải insert testcase vào `history.db` trước khi ghi run**, nếu
  không `get_pending_review`'s `JOIN testcases` sẽ âm thầm bỏ sót kết
  quả của chính testcase đó. (Task 6)

---

### Task 1: Harden the script-generation prompt (safety, runnable contract, credentials)

**Files:**
- Modify: `qwen-test-automation/qwen_test_automation/llm/script_generator.py`
- Modify: `qwen-test-automation/tests/llm/test_script_generator.py`

**Interfaces:**
- Consumes: none new
- Produces: `generate_script` unchanged in signature; its prompt now also
  instructs Qwen to (a) never submit a real transaction, (b) write a
  standalone script runnable as `python script.py` using
  `playwright.sync_api` directly (web) with no pytest fixtures, and (c)
  read login credentials from the environment variables
  `QWEN_TEST_ACCOUNT`, `QWEN_TEST_PASSWORD`, `QWEN_TEST_OTP` instead of
  hard-coding them.

- [ ] **Step 1: Write the failing tests**

```python
# tests/llm/test_script_generator.py (append)
def test_generate_script_prompt_forbids_real_transaction_submit():
    client = FakeClient("script")
    generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    assert "không bấm" in client.last_prompt or "dừng trước" in client.last_prompt

def test_generate_script_prompt_requires_standalone_sync_api_script():
    client = FakeClient("script")
    generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    assert "playwright.sync_api" in client.last_prompt
    assert "pytest" in client.last_prompt  # instructed not to use it

def test_generate_script_prompt_tells_qwen_to_read_credentials_from_env():
    client = FakeClient("script")
    generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    assert "QWEN_TEST_ACCOUNT" in client.last_prompt
    assert "QWEN_TEST_PASSWORD" in client.last_prompt
    assert "QWEN_TEST_OTP" in client.last_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/llm/test_script_generator.py -v`
Expected: FAIL — the current prompt contains none of these phrases

- [ ] **Step 3: Update `_PROMPT_TEMPLATE` (and/or `_WEB_INSTRUCTION`) in `script_generator.py`**

Add, after the existing template content, three always-included
instruction lines (in Vietnamese, matching the rest of this project's
prompts): one stating the script must stop before confirming/submitting
any real transaction (placing/editing/cancelling an order, transferring
or withdrawing money) and must contain the phrase "dừng trước" or
"không bấm" literally; one stating the script must be standalone,
runnable as `python script.py`, using `playwright.sync_api` directly and
must **not** use `pytest` (state this explicitly, e.g. "không dùng
pytest"); one stating that when the testcase needs login, the script
must read the account, password and OTP from the environment variables
`QWEN_TEST_ACCOUNT`, `QWEN_TEST_PASSWORD`, `QWEN_TEST_OTP` and must never
hard-code or print them. These apply regardless of platform (keep them
in the shared `_PROMPT_TEMPLATE`, not only `_WEB_INSTRUCTION`, so Task 1
of the later mobile-runner plan inherits them too).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/llm/test_script_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/llm/script_generator.py qwen-test-automation/tests/llm/test_script_generator.py
git commit -m "feat: harden script-generation prompt with safety, contract and credential rules"
```

---

### Task 2: Safety gate

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/runner/__init__.py`
- Create: `qwen-test-automation/qwen_test_automation/runner/safety_gate.py`
- Test: `qwen-test-automation/tests/runner/test_safety_gate.py`

**Interfaces:**
- Consumes: `is_host_allowed` (Foundation `config.host_allowlist`)
- Produces: `HostNotAllowedError(Exception)`;
  `assert_host_allowed(url: str, allowed_hosts: set) -> None` (raises
  `HostNotAllowedError` naming the host if
  `is_host_allowed(hostname, allowed_hosts)` is `False`; does nothing
  otherwise)

- [ ] **Step 1: Write the failing tests**

```python
# tests/runner/test_safety_gate.py
import pytest
from qwen_test_automation.runner.safety_gate import assert_host_allowed, HostNotAllowedError

def test_assert_host_allowed_passes_for_allowed_host():
    assert_host_allowed("https://uat-wts.shinhan.internal/login", {"uat-wts.shinhan.internal"})

def test_assert_host_allowed_raises_for_disallowed_host():
    with pytest.raises(HostNotAllowedError, match="prod-wts.shinhan.com"):
        assert_host_allowed("https://prod-wts.shinhan.com/login", {"uat-wts.shinhan.internal"})

def test_assert_host_allowed_raises_when_allowlist_empty():
    with pytest.raises(HostNotAllowedError):
        assert_host_allowed("https://uat-wts.shinhan.internal/login", set())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/runner/test_safety_gate.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `safety_gate.py`**

Use `urllib.parse.urlparse(url).hostname` to extract the host. If
`not is_host_allowed(host, allowed_hosts)`, raise
`HostNotAllowedError(f"host not in allowlist, refusing to run: {host} (from {url})")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/runner/test_safety_gate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/runner/__init__.py qwen-test-automation/qwen_test_automation/runner/safety_gate.py qwen-test-automation/tests/runner/test_safety_gate.py
git commit -m "feat: add host safety gate for the runner"
```

---

### Task 3: Script store

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/runner/script_store.py`
- Test: `qwen-test-automation/tests/runner/test_script_store.py`

**Interfaces:**
- Consumes: none
- Produces: `script_path_for(testcase_id: str, scripts_dir: str) -> str`
  (`os.path.join(scripts_dir, f"{testcase_id}.py")`);
  `load_script(testcase_id: str, scripts_dir: str) -> str | None` (`None`
  if the file doesn't exist); `save_script(testcase_id: str, source: str, scripts_dir: str) -> str`
  (creates `scripts_dir` if missing, writes the file, returns its path)

- [ ] **Step 1: Write the failing tests**

```python
# tests/runner/test_script_store.py
from qwen_test_automation.runner.script_store import (
    script_path_for, load_script, save_script,
)

def test_load_script_missing_returns_none(tmp_path):
    assert load_script("TC-001", str(tmp_path / "scripts")) is None

def test_save_then_load_round_trips(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    path = save_script("TC-001", "print('hello')", scripts_dir)
    assert path == script_path_for("TC-001", scripts_dir)
    assert load_script("TC-001", scripts_dir) == "print('hello')"

def test_save_script_creates_missing_directory(tmp_path):
    scripts_dir = str(tmp_path / "does" / "not" / "exist")
    save_script("TC-001", "print('hi')", scripts_dir)
    assert load_script("TC-001", scripts_dir) == "print('hi')"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/runner/test_script_store.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `script_store.py`**

Plain `os.path`/file I/O, UTF-8 encoding for read and write.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/runner/test_script_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/runner/script_store.py qwen-test-automation/tests/runner/test_script_store.py
git commit -m "feat: add per-testcase script store"
```

---

### Task 4: Failure triage

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/runner/failure_triage.py`
- Test: `qwen-test-automation/tests/runner/test_failure_triage.py`

**Interfaces:**
- Consumes: none
- Produces: `classify_failure(stderr: str) -> str` (returns `"assertion"`
  if `"AssertionError"` appears in `stderr`, else `"locator"` — the safe
  default for any failure that doesn't match a known assertion signature)

- [ ] **Step 1: Write the failing tests**

```python
# tests/runner/test_failure_triage.py
from qwen_test_automation.runner.failure_triage import classify_failure

def test_classify_assertion_error_as_assertion():
    stderr = "Traceback (most recent call last):\n  ...\nAssertionError: expected Dashboard, got Login"
    assert classify_failure(stderr) == "assertion"

def test_classify_timeout_error_as_locator():
    stderr = "playwright._impl._api_types.TimeoutError: Timeout 30000ms exceeded."
    assert classify_failure(stderr) == "locator"

def test_classify_unknown_or_empty_defaults_to_locator():
    assert classify_failure("") == "locator"
    assert classify_failure("SomeWeirdCrash: boom") == "locator"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/runner/test_failure_triage.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `failure_triage.py`**

`classify_failure` is a one-line check: `"AssertionError" in stderr`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/runner/test_failure_triage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/runner/failure_triage.py qwen-test-automation/tests/runner/test_failure_triage.py
git commit -m "feat: add failure triage classifier"
```

---

### Task 5: Script executor

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/runner/playwright_executor.py`
- Test: `qwen-test-automation/tests/runner/test_playwright_executor.py`

**Interfaces:**
- Consumes: none
- Produces: `ExecutionTimeoutError(Exception)`; `ExecutionResult` (plain
  object with `.returncode: int`, `.stdout: str`, `.stderr: str`);
  `run_script(script_path: str, timeout: int = 60, env: dict | None = None) -> ExecutionResult`
  (runs `[sys.executable, script_path]` via `subprocess.run`, merging
  `env` into a copy of the current environment; raises
  `ExecutionTimeoutError` if the process doesn't finish within `timeout`
  seconds)

- [ ] **Step 1: Write the failing tests**

```python
# tests/runner/test_playwright_executor.py
import pytest
from qwen_test_automation.runner.playwright_executor import (
    run_script, ExecutionTimeoutError,
)

def test_run_script_success(tmp_path):
    p = tmp_path / "ok.py"
    p.write_text("import sys\nsys.exit(0)\n")
    result = run_script(str(p))
    assert result.returncode == 0

def test_run_script_failure_captures_stderr(tmp_path):
    p = tmp_path / "bad.py"
    p.write_text("assert False, 'boom'\n")
    result = run_script(str(p))
    assert result.returncode != 0
    assert "boom" in result.stderr

def test_run_script_passes_extra_env_vars(tmp_path):
    p = tmp_path / "env_check.py"
    p.write_text(
        "import os, sys\n"
        "sys.exit(0 if os.environ.get('MY_VAR') == 'hello' else 1)\n"
    )
    result = run_script(str(p), env={"MY_VAR": "hello"})
    assert result.returncode == 0

def test_run_script_raises_on_timeout(tmp_path):
    p = tmp_path / "slow.py"
    p.write_text("import time\ntime.sleep(5)\n")
    with pytest.raises(ExecutionTimeoutError):
        run_script(str(p), timeout=1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/runner/test_playwright_executor.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `playwright_executor.py`**

```python
import os
import subprocess
import sys


class ExecutionTimeoutError(Exception):
    pass


class ExecutionResult:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
```
`run_script` builds `full_env = {**os.environ, **(env or {})}`, calls
`subprocess.run([sys.executable, script_path], capture_output=True, text=True, timeout=timeout, env=full_env)`
inside `try/except subprocess.TimeoutExpired as e: raise ExecutionTimeoutError(f"script did not finish within {timeout}s: {script_path}") from e`,
and returns an `ExecutionResult` from the completed process.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/runner/test_playwright_executor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/runner/playwright_executor.py qwen-test-automation/tests/runner/test_playwright_executor.py
git commit -m "feat: add subprocess-based script executor"
```

---

### Task 6: Web runner orchestration

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/runner/web_runner.py`
- Test: `qwen-test-automation/tests/runner/test_web_runner.py`

**Interfaces:**
- Consumes: `assert_host_allowed`/`HostNotAllowedError` (Task 2),
  `load_script`/`save_script`/`script_path_for` (Task 3),
  `classify_failure` (Task 4), `run_script` (Task 5), `generate_script`
  (Foundation), `insert_testcase`/`get_testcase`/`record_run`
  (Foundation `history.db`)
- Produces: `run_web_testcase(testcase: TestCase, url: str, client, model: str, allowed_hosts: set, scripts_dir: str, conn, credentials: dict | None = None, account: str | None = None) -> str`
  (returns `"pass"`, `"fail"`, or `"pending_claude_review"` — the same
  value it records via `record_run`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/runner/test_web_runner.py
from qwen_test_automation.models import TestCase
from qwen_test_automation.history.db import init_db, get_pending_review
from qwen_test_automation.runner.safety_gate import HostNotAllowedError
from qwen_test_automation.runner.script_store import save_script
from qwen_test_automation.runner.web_runner import run_web_testcase
import pytest


class FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text
    def generate(self, model, prompt, images=None):
        return self.response_text


def make_testcase():
    return TestCase(
        id="TC-001", feature="Login", precondition="Account exists",
        steps=["Open login page", "Login"], expected_result="Dashboard shown",
        platform="WTS",
    )


def test_run_web_testcase_refuses_disallowed_host(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    client = FakeClient("ignored")
    with pytest.raises(HostNotAllowedError):
        run_web_testcase(
            make_testcase(), "https://prod.example.com", client, "m",
            allowed_hosts=set(), scripts_dir=str(tmp_path / "scripts"), conn=conn,
        )


def test_run_web_testcase_generates_script_and_passes(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    client = FakeClient("import sys\nsys.exit(0)\n")
    status = run_web_testcase(
        make_testcase(), "https://uat.example.internal", client, "m",
        allowed_hosts={"uat.example.internal"}, scripts_dir=str(tmp_path / "scripts"), conn=conn,
    )
    assert status == "pass"


def test_run_web_testcase_reuses_existing_script_without_regenerating(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    save_script("TC-001", "import sys\nsys.exit(0)\n", scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    client = FakeClient("not valid python at all")  # must never be run
    status = run_web_testcase(
        make_testcase(), "https://uat.example.internal", client, "m",
        allowed_hosts={"uat.example.internal"}, scripts_dir=scripts_dir, conn=conn,
    )
    assert status == "pass"


def test_run_web_testcase_assertion_failure_retries_once_then_fails(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    client = FakeClient("assert False, 'boom'\n")
    status = run_web_testcase(
        make_testcase(), "https://uat.example.internal", client, "m",
        allowed_hosts={"uat.example.internal"}, scripts_dir=str(tmp_path / "scripts"), conn=conn,
    )
    assert status == "fail"
    assert get_pending_review(conn) == []


def test_run_web_testcase_locator_failure_marks_pending_review(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    client = FakeClient("raise TimeoutError('Timeout 30000ms exceeded')\n")
    status = run_web_testcase(
        make_testcase(), "https://uat.example.internal", client, "m",
        allowed_hosts={"uat.example.internal"}, scripts_dir=str(tmp_path / "scripts"), conn=conn,
    )
    assert status == "pending_claude_review"
    pending = get_pending_review(conn)
    assert len(pending) == 1
    assert pending[0]["testcase_id"] == "TC-001"


def test_run_web_testcase_passes_credentials_as_env_vars(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    script = (
        "import os, sys\n"
        "ok = (os.environ.get('QWEN_TEST_ACCOUNT') == '0000000001'\n"
        "      and os.environ.get('QWEN_TEST_PASSWORD') == 'x'\n"
        "      and os.environ.get('QWEN_TEST_OTP') == '000000')\n"
        "sys.exit(0 if ok else 1)\n"
    )
    client = FakeClient(script)
    credentials = {"0000000001": {"password": "x", "default_otp": "000000"}}
    status = run_web_testcase(
        make_testcase(), "https://uat.example.internal", client, "m",
        allowed_hosts={"uat.example.internal"}, scripts_dir=str(tmp_path / "scripts"), conn=conn,
        credentials=credentials, account="0000000001",
    )
    assert status == "pass"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/runner/test_web_runner.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `web_runner.py`**

```python
def run_web_testcase(testcase, url, client, model, allowed_hosts, scripts_dir, conn, credentials=None, account=None):
    assert_host_allowed(url, allowed_hosts)

    if get_testcase(conn, testcase.id) is None:
        insert_testcase(conn, testcase)

    existing = load_script(testcase.id, scripts_dir)
    if existing is None:
        source = generate_script(testcase, client=client, model=model)
        path = save_script(testcase.id, source, scripts_dir)
    else:
        path = script_path_for(testcase.id, scripts_dir)

    env = None
    if account and credentials:
        acc = credentials[account]
        env = {
            "QWEN_TEST_ACCOUNT": account,
            "QWEN_TEST_PASSWORD": acc["password"],
            "QWEN_TEST_OTP": acc["default_otp"],
        }

    result = run_script(path, env=env)
    if result.returncode == 0:
        record_run(conn, testcase.id, "pass", None, "")
        return "pass"

    failure_type = classify_failure(result.stderr)
    if failure_type == "assertion":
        retry = run_script(path, env=env)
        if retry.returncode == 0:
            record_run(conn, testcase.id, "pass", None, "")
            return "pass"
        record_run(conn, testcase.id, "fail", "assertion", retry.stderr[:500])
        return "fail"

    record_run(conn, testcase.id, "pending_claude_review", "locator", result.stderr[:500])
    return "pending_claude_review"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/runner/test_web_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/runner/web_runner.py qwen-test-automation/tests/runner/test_web_runner.py
git commit -m "feat: add web runner orchestration"
```
