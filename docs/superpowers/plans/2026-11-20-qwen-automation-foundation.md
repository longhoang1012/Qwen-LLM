# Qwen Automation Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared foundation — config/credential loading, the shared
`TestCase` model, the SQLite history store, and the Ollama (Qwen) client used
to generate testcases and automation scripts — that every later plan
(ingestion, web runner, mobile runner, reporting) depends on.

**Architecture:** A small `qwen-test-automation/` project whose installable
Python package is `qwen_test_automation/` (underscore, so it can be
imported — the project folder itself keeps the hyphenated name from the
design doc). `config/` loads secrets and the host allowlist from local,
gitignored JSON files, failing safe (deny-by-default) when the allowlist is
absent. `models.py` defines the one shared `TestCase` shape. `history/db.py`
wraps a single SQLite file recording testcases and run results. `llm/`
wraps the Ollama HTTP API behind an injectable transport so callers (and
tests) never need a live Ollama server running, then builds
`generate_testcases()` and `generate_script()` on top of it.

**Tech Stack:** Python 3.11+ (venv), `requests` for HTTP, `pytest` (>=8, for
its built-in `pythonpath` ini option) for tests, stdlib `sqlite3`,
`dataclasses`, `json`. No other runtime dependency in this plan.

**Spec:** [docs/superpowers/specs/2026-11-20-local-qwen-automation-design.md](../specs/2026-11-20-local-qwen-automation-design.md)

## Global Constraints

- Máy M2 Pro, 16GB RAM — không tải model trong phạm vi plan này (chỉ gọi API
  Ollama khi có); model name luôn là tham số, không hard-code version cụ thể.
- Credential (account, password, OTP) không bao giờ xuất hiện plaintext trong
  code, log, hay git history — chỉ đọc từ file local đã gitignore.
- Safety/host allowlist mặc định **deny-all** khi chưa cấu hình — không được
  coi "chưa cấu hình" là "cho phép tất cả".
- Mọi lỗi từ việc đọc config hoặc gọi Ollama phải là một exception rõ ràng,
  có thông điệp hành động được (không phải traceback thô của thư viện gốc).

## Review Focus

- LLM trả JSON lỗi hoặc thiếu field khi sinh testcase → `generate_testcases`
  phải raise lỗi rõ ràng, không được âm thầm trả danh sách rỗng hoặc crash mơ
  hồ. (Task 5)
- File `credentials.local.json` không tồn tại hoặc sai định dạng → loader
  phải raise lỗi actionable, không phải `KeyError`/`JSONDecodeError` trần trụi.
  (Task 2)
- Chưa cấu hình host allowlist (file chưa tồn tại) → phải trả về tập rỗng
  (deny-all), không phải lỗi và không phải allow-all. (Task 2)
- Ollama server không chạy (connection refused) → `OllamaClient.generate`
  phải raise một exception riêng phân biệt được với lỗi HTTP khác. (Task 4)
- `generate_script` nhận `testcase.platform` không nằm trong 4 giá trị hợp lệ
  (WTS/MWTS/MTS-Android/MTS-iOS) → phải raise `ValueError` ngay, không sinh
  script sai lặng lẽ. (Task 6)

---

### Task 1: Project scaffolding + shared `TestCase` model

**Files:**
- Create: `qwen-test-automation/pyproject.toml`
- Create: `qwen-test-automation/requirements.txt`
- Create: `qwen-test-automation/qwen_test_automation/__init__.py`
- Create: `qwen-test-automation/qwen_test_automation/models.py`
- Create: `qwen-test-automation/tests/__init__.py`
- Test: `qwen-test-automation/tests/test_models.py`

**Interfaces:**
- Produces: `TestCase` dataclass with fields `id: str`, `feature: str`,
  `precondition: str`, `steps: list[str]`, `expected_result: str`,
  `platform: str`. `VALID_PLATFORMS: frozenset[str]` =
  `{"WTS", "MWTS", "MTS-Android", "MTS-iOS"}`. `TestCase.to_dict() -> dict`
  and `TestCase.from_dict(data: dict) -> TestCase`.

- [ ] **Step 1: Scaffold the project**

Create `qwen-test-automation/pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```
Create `qwen-test-automation/requirements.txt`:
```
pytest>=8.0
```
Create empty `qwen-test-automation/qwen_test_automation/__init__.py` and
`qwen-test-automation/tests/__init__.py`. Set up a venv under
`qwen-test-automation/.venv` and `pip install -r requirements.txt` (the
venv itself is not committed — add `qwen-test-automation/.venv/` to
`.gitignore` in this step too).

- [ ] **Step 2: Write the failing test**

```python
# tests/test_models.py
from qwen_test_automation.models import TestCase, VALID_PLATFORMS

def test_valid_platforms_contains_expected_four():
    assert VALID_PLATFORMS == {"WTS", "MWTS", "MTS-Android", "MTS-iOS"}

def test_testcase_round_trips_through_dict():
    tc = TestCase(
        id="TC-001",
        feature="Login",
        precondition="Account exists",
        steps=["Open app", "Enter account", "Enter password", "Tap login"],
        expected_result="User lands on dashboard",
        platform="MTS-Android",
    )
    data = tc.to_dict()
    restored = TestCase.from_dict(data)
    assert restored == tc
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `qwen-test-automation/`): `.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL with "No module named 'qwen_test_automation'"

- [ ] **Step 4: Implement `TestCase` and `VALID_PLATFORMS` in `qwen_test_automation/models.py`**

Use `@dataclass`. `to_dict`/`from_dict` are a direct field mapping (steps
stays a list, no nested encoding needed at this layer).

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add qwen-test-automation/pyproject.toml qwen-test-automation/requirements.txt qwen-test-automation/qwen_test_automation/ qwen-test-automation/tests/ .gitignore
git commit -m "feat: scaffold qwen-test-automation project and shared TestCase model"
```

---

### Task 2: Config loaders (credentials + host allowlist)

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/config/__init__.py`
- Create: `qwen-test-automation/qwen_test_automation/config/credentials.py`
- Create: `qwen-test-automation/qwen_test_automation/config/host_allowlist.py`
- Create: `qwen-test-automation/config_examples/credentials.local.json.example`
- Create: `qwen-test-automation/config_examples/host_allowlist.local.json.example`
- Modify: `.gitignore` (add `qwen-test-automation/config_local/`)
- Test: `qwen-test-automation/tests/config/test_credentials.py`
- Test: `qwen-test-automation/tests/config/test_host_allowlist.py`

**Interfaces:**
- Consumes: none
- Produces: `CredentialsError(Exception)`; `load_credentials(path: str) -> dict[str, dict]`
  mapping account number to `{"password": str, "default_otp": str}`.
  `HostAllowlistError(Exception)`; `load_allowed_hosts(path: str) -> set[str]`;
  `is_host_allowed(host: str, allowed_hosts: set[str]) -> bool`.

Real secrets live in `qwen-test-automation/config_local/credentials.json`
and `qwen-test-automation/config_local/host_allowlist.json` at runtime (a
directory, gitignored wholesale, created manually by whoever runs this —
not created by this task). The `config_examples/*.example` files are
templates only, checked into git with placeholder values.

- [ ] **Step 1: Write the failing tests**

```python
# tests/config/test_credentials.py
import json
import pytest
from qwen_test_automation.config.credentials import load_credentials, CredentialsError

def test_load_credentials_returns_mapping(tmp_path):
    p = tmp_path / "credentials.json"
    p.write_text(json.dumps({
        "0000000001": {"password": "x", "default_otp": "000000"}
    }))
    creds = load_credentials(str(p))
    assert creds["0000000001"]["default_otp"] == "000000"

def test_load_credentials_missing_file_raises_actionable_error(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(CredentialsError, match="not found"):
        load_credentials(str(missing))

def test_load_credentials_malformed_json_raises_actionable_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    with pytest.raises(CredentialsError, match="invalid JSON"):
        load_credentials(str(p))
```

```python
# tests/config/test_host_allowlist.py
import json
import pytest
from qwen_test_automation.config.host_allowlist import (
    load_allowed_hosts, is_host_allowed, HostAllowlistError,
)

def test_missing_file_defaults_to_deny_all(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    assert load_allowed_hosts(str(missing)) == set()

def test_load_allowed_hosts_from_file(tmp_path):
    p = tmp_path / "host_allowlist.json"
    p.write_text(json.dumps(["uat-wts.shinhan.internal"]))
    assert load_allowed_hosts(str(p)) == {"uat-wts.shinhan.internal"}

def test_malformed_file_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("[not valid")
    with pytest.raises(HostAllowlistError, match="invalid JSON"):
        load_allowed_hosts(str(p))

def test_is_host_allowed_true_and_false():
    allowed = {"uat-wts.shinhan.internal"}
    assert is_host_allowed("uat-wts.shinhan.internal", allowed) is True
    assert is_host_allowed("prod-wts.shinhan.com", allowed) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/config/ -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `credentials.py` and `host_allowlist.py`**

`load_credentials`: read file, raise `CredentialsError("credentials file not
found: {path}")` on `FileNotFoundError`, raise
`CredentialsError("credentials file has invalid JSON: {path}")` on
`json.JSONDecodeError`, otherwise return the parsed dict.

`load_allowed_hosts`: on `FileNotFoundError` return `set()` (deny-all
default — do not raise). On `json.JSONDecodeError` raise
`HostAllowlistError("host allowlist file has invalid JSON: {path}")`.
Otherwise return `set(parsed_list)`. `is_host_allowed` is a plain
membership check.

- [ ] **Step 4: Create the example config files (not real secrets)**

`config_examples/credentials.local.json.example`:
```json
{
  "0000000000": { "password": "CHANGE_ME", "default_otp": "000000" }
}
```

`config_examples/host_allowlist.local.json.example`:
```json
["uat-wts.example.internal", "uat-mwts.example.internal"]
```

- [ ] **Step 5: Add gitignore entry**

Append to `.gitignore`:
```
# Qwen automation local secrets — never commit real credentials/hosts
qwen-test-automation/config_local/
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/config/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/config/ qwen-test-automation/config_examples/ qwen-test-automation/tests/config/ .gitignore
git commit -m "feat: add credentials and host-allowlist config loaders"
```

---

### Task 3: History DB (SQLite)

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/history/__init__.py`
- Create: `qwen-test-automation/qwen_test_automation/history/db.py`
- Test: `qwen-test-automation/tests/history/test_db.py`

**Interfaces:**
- Consumes: `TestCase` from Task 1 (`qwen_test_automation.models`)
- Produces: `init_db(db_path: str) -> sqlite3.Connection`;
  `insert_testcase(conn, testcase: TestCase) -> None`;
  `get_testcase(conn, testcase_id: str) -> TestCase | None`;
  `record_run(conn, testcase_id: str, status: str, failure_type: str | None, message: str) -> int`
  (returns the new run's rowid, `status` one of `"pass"`, `"fail"`,
  `"pending_claude_review"`, `failure_type` one of `"locator"`,
  `"assertion"`, `None`);
  `get_pending_review(conn) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/history/test_db.py
from qwen_test_automation.models import TestCase
from qwen_test_automation.history.db import (
    init_db, insert_testcase, get_testcase, record_run, get_pending_review,
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/history/ -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `history/db.py`**

Schema:
```sql
CREATE TABLE IF NOT EXISTS testcases (
  id TEXT PRIMARY KEY, feature TEXT, precondition TEXT,
  steps_json TEXT, expected_result TEXT, platform TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  testcase_id TEXT NOT NULL REFERENCES testcases(id),
  status TEXT NOT NULL CHECK(status IN ('pass','fail','pending_claude_review')),
  failure_type TEXT CHECK(failure_type IN ('locator','assertion') OR failure_type IS NULL),
  message TEXT, started_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```
`steps_json` stores `json.dumps(testcase.steps)`; `get_testcase` parses it
back. `init_db` opens the connection with `row_factory = sqlite3.Row` and
runs the `CREATE TABLE IF NOT EXISTS` statements. `get_pending_review`
selects runs with `status = 'pending_claude_review'` joined to their
testcase, returning one `dict` per row (most recent run per testcase only —
order by `id DESC`, de-dup by `testcase_id` in Python).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/history/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/history/ qwen-test-automation/tests/history/
git commit -m "feat: add SQLite history store for testcases and runs"
```

---

### Task 4: Ollama client

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/llm/__init__.py`
- Create: `qwen-test-automation/qwen_test_automation/llm/ollama_client.py`
- Modify: `qwen-test-automation/requirements.txt` (add `requests`)
- Test: `qwen-test-automation/tests/llm/test_ollama_client.py`

**Interfaces:**
- Consumes: none
- Produces: `OllamaError(Exception)`; `OllamaConnectionError(OllamaError)`;
  `OllamaResponseError(OllamaError)`; class `OllamaClient(base_url: str = "http://localhost:11434", post=requests.post)`
  with method `generate(self, model: str, prompt: str, images: list[str] | None = None) -> str`
  (`images` are base64-encoded strings, forwarded as Ollama's `images` field;
  returns the `"response"` field of Ollama's JSON reply; calls
  `self.post(f"{base_url}/api/generate", json={"model": model, "prompt": prompt, "images": images, "stream": False}, timeout=120)`).

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_ollama_client.py
import pytest
from qwen_test_automation.llm.ollama_client import (
    OllamaClient, OllamaConnectionError, OllamaResponseError,
)

class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload

def test_generate_returns_response_text():
    def fake_post(url, json, timeout):
        assert url == "http://localhost:11434/api/generate"
        assert json["model"] == "qwen2.5:7b"
        assert json["prompt"] == "hello"
        return FakeResponse(200, {"response": "hi there"})
    client = OllamaClient(post=fake_post)
    assert client.generate(model="qwen2.5:7b", prompt="hello") == "hi there"

def test_generate_raises_connection_error_when_post_raises():
    import requests
    def fake_post(url, json, timeout):
        raise requests.ConnectionError("refused")
    client = OllamaClient(post=fake_post)
    with pytest.raises(OllamaConnectionError):
        client.generate(model="qwen2.5:7b", prompt="hello")

def test_generate_raises_response_error_on_non_200():
    def fake_post(url, json, timeout):
        return FakeResponse(500, {"error": "boom"})
    client = OllamaClient(post=fake_post)
    with pytest.raises(OllamaResponseError):
        client.generate(model="qwen2.5:7b", prompt="hello")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/llm/test_ollama_client.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Add `requests` to `requirements.txt` and implement `ollama_client.py`**

Append `requests>=2.31` to `qwen-test-automation/requirements.txt`, then
`.venv/bin/pip install -r requirements.txt`.

`OllamaClient.generate`: call `self.post(...)` inside `try/except requests.RequestException as e: raise OllamaConnectionError(str(e)) from e`; if the returned object's `status_code != 200`, raise
`OllamaResponseError(f"Ollama returned HTTP {resp.status_code}")`; otherwise
return `resp.json()["response"]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/llm/test_ollama_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/llm/__init__.py qwen-test-automation/qwen_test_automation/llm/ollama_client.py qwen-test-automation/requirements.txt qwen-test-automation/tests/llm/test_ollama_client.py
git commit -m "feat: add Ollama client wrapper"
```

---

### Task 5: Testcase generator

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/llm/testcase_generator.py`
- Test: `qwen-test-automation/tests/llm/test_testcase_generator.py`

**Interfaces:**
- Consumes: `OllamaClient` (Task 4), `TestCase`/`VALID_PLATFORMS` (Task 1)
- Produces: `TestcaseParseError(Exception)`;
  `generate_testcases(doc_text: str, client: OllamaClient, model: str, images: list[str] | None = None) -> list[TestCase]`

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_testcase_generator.py
import json
import pytest
from qwen_test_automation.llm.testcase_generator import (
    generate_testcases, TestcaseParseError,
)

class FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text
    def generate(self, model, prompt, images=None):
        return self.response_text

def test_generate_testcases_parses_valid_json_array():
    payload = json.dumps([{
        "id": "TC-001", "feature": "Login", "precondition": "Account exists",
        "steps": ["Open app", "Login"], "expected_result": "Dashboard shown",
        "platform": "MTS-Android",
    }])
    client = FakeClient(payload)
    result = generate_testcases("some doc text", client=client, model="qwen2.5:7b")
    assert len(result) == 1
    assert result[0].id == "TC-001"
    assert result[0].platform == "MTS-Android"

def test_generate_testcases_raises_on_malformed_json():
    client = FakeClient("not json at all")
    with pytest.raises(TestcaseParseError):
        generate_testcases("some doc text", client=client, model="qwen2.5:7b")

def test_generate_testcases_raises_on_invalid_platform():
    payload = json.dumps([{
        "id": "TC-001", "feature": "Login", "precondition": "",
        "steps": ["Open app"], "expected_result": "ok",
        "platform": "NotAPlatform",
    }])
    client = FakeClient(payload)
    with pytest.raises(TestcaseParseError):
        generate_testcases("some doc text", client=client, model="qwen2.5:7b")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/llm/test_testcase_generator.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `testcase_generator.py`**

Build a prompt instructing Qwen to output only a JSON array of objects with
exactly the `TestCase` fields (`id, feature, precondition, steps,
expected_result, platform`), call `client.generate(model=model,
prompt=prompt, images=images)`, then `json.loads` the result. On
`json.JSONDecodeError` or non-list result, raise
`TestcaseParseError(f"Qwen did not return a valid testcase JSON array: {e}")`.
For each item, build a `TestCase` via `TestCase.from_dict`; if
`platform not in VALID_PLATFORMS`, raise
`TestcaseParseError(f"testcase {item.get('id')} has invalid platform: {item.get('platform')}")`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/llm/test_testcase_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/llm/testcase_generator.py qwen-test-automation/tests/llm/test_testcase_generator.py
git commit -m "feat: add testcase generator over Ollama"
```

---

### Task 6: Script generator

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/llm/script_generator.py`
- Test: `qwen-test-automation/tests/llm/test_script_generator.py`

**Interfaces:**
- Consumes: `OllamaClient` (Task 4), `TestCase`/`VALID_PLATFORMS` (Task 1)
- Produces: `generate_script(testcase: TestCase, client: OllamaClient, model: str) -> str`
  (raises `ValueError` if `testcase.platform not in VALID_PLATFORMS`)

- [ ] **Step 1: Write the failing test**

```python
# tests/llm/test_script_generator.py
import pytest
from qwen_test_automation.models import TestCase
from qwen_test_automation.llm.script_generator import generate_script

class FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text
        self.last_prompt = None
    def generate(self, model, prompt, images=None):
        self.last_prompt = prompt
        return self.response_text

def make_testcase(platform="WTS"):
    return TestCase(
        id="TC-001", feature="Login", precondition="Account exists",
        steps=["Open login page", "Enter account", "Submit"],
        expected_result="Dashboard shown", platform=platform,
    )

def test_generate_script_returns_client_response():
    client = FakeClient("<generated playwright script>")
    script = generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    assert script == "<generated playwright script>"
    assert "TC-001" in client.last_prompt

def test_generate_script_raises_on_invalid_platform():
    tc = make_testcase("WTS")
    tc.platform = "NotAPlatform"
    client = FakeClient("irrelevant")
    with pytest.raises(ValueError):
        generate_script(tc, client=client, model="qwen2.5-coder:7b")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/llm/test_script_generator.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `script_generator.py`**

If `testcase.platform not in VALID_PLATFORMS`, raise
`ValueError(f"unknown platform: {testcase.platform}")` before calling the
client. Otherwise build a prompt embedding the testcase's `id`, `feature`,
`steps`, and `expected_result`, and a platform-specific instruction: `"WTS"`/`"MWTS"`
→ ask for a Playwright script; `"MTS-Android"`/`"MTS-iOS"` → ask for an
Appium script. Call `client.generate(model=model, prompt=prompt)` and
return its result unmodified (script review/validation is a later plan's
concern).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/llm/test_script_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/llm/script_generator.py qwen-test-automation/tests/llm/test_script_generator.py
git commit -m "feat: add script generator over Ollama"
```
