# Qwen Automation Excel Readback + Runner CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop between Ingestion and the Web Runner: read a
reviewed/edited QC testcase Excel file back into `TestScenario`s, and add
two CLI subcommands so using the Web Runner from day to day needs no
hand-written Python — `generate-script` (phase 2, review-only) and
`run-tests` (phase 3, runs what's already been reviewed).

**Architecture:** `ingestion/excel_import.py` mirrors `excel_export.py`'s
column layout in reverse — one `TestScenario` per data row, with
`applicable_platforms` derived from "which platform columns aren't
exactly `N/A`" (so a cell a QC has already marked `Pass`/`Fail` still
counts as applicable; only `N/A` or blank excludes it). `cli.py` gets two
thin subcommands built on small, directly-testable helper functions
(`_generate_scripts`, `_run_tests`) that loop over scenarios × their
applicable platforms, skipping mobile platforms (not supported by this
CLI yet) and calling straight into the already-reviewed
`ensure_script_generated`/`run_web_testcase`. Neither subcommand ever
generates and runs a script in the same call — that boundary, fixed in
the Web Runner's final review, is preserved here by keeping them as two
separate subcommands.

**Tech Stack:** Same venv as before. No new dependency (`openpyxl`
already present).

**Spec:** [docs/superpowers/specs/2026-11-20-local-qwen-automation-design.md](../specs/2026-11-20-local-qwen-automation-design.md)
(§10 — QC Excel format this reads back; the 2026-11-23 note on §6 about
generation and execution being separate steps, which this plan's CLI
boundary must also respect)

## Global Constraints

- `generate-script` chỉ sinh/lưu script, không bao giờ chạy gì.
- `run-tests` chỉ chạy script đã có sẵn trong `scripts_dir`, không bao giờ
  tự gọi Qwen sinh script mới (giữ đúng ranh giới review đã sửa ở Web
  Runner).
- Nền tảng mobile (MTS-Android, MTS-iOS) chưa được CLI này hỗ trợ — phải
  bỏ qua rõ ràng (có ghi nhận), không được âm thầm bỏ sót hay crash.
- Một cột nền tảng được coi là "áp dụng" nếu giá trị khác đúng chuỗi
  `"N/A"` (và khác rỗng/`None`) — một ô QC đã tự ghi `Pass`/`Fail` vẫn
  phải được coi là áp dụng.

## Review Focus

- Cột "Bước thực hiện" rỗng/`None` → `read_scenarios_from_excel` phải trả
  về `steps=[]`, không crash. (Task 1)
- Cột nền tảng có giá trị khác `"N/A"` nhưng cũng khác `"Not run"` (vd
  QC tự ghi `"Pass"`) → vẫn phải được tính là áp dụng (applicable).
  (Task 1)
- Scenario chỉ áp dụng cho nền tảng mobile (MTS-Android/MTS-iOS) →
  `_generate_scripts`/`_run_tests` phải bỏ qua có ghi nhận, không crash,
  không âm thầm biến mất khỏi kết quả trả về. (Task 2)
- `run-tests` trỏ vào host không nằm trong allowlist → phải dừng ngay từ
  lần gọi đầu tiên (raise), không tiếp tục lặp qua từng testcase còn lại
  gây lỗi lặp lại vô ích. (Task 2)
- File Excel chỉ có header, không có dòng dữ liệu nào → cả
  `read_scenarios_from_excel` và các hàm CLI phải trả về danh sách rỗng,
  không crash. (Task 1 + Task 2)

---

### Task 1: Excel readback

**Files:**
- Modify: `qwen-test-automation/qwen_test_automation/ingestion/excel_export.py`
  (rename `_PLATFORM_COLUMNS` → `PLATFORM_COLUMNS`, public — no behavior
  change)
- Create: `qwen-test-automation/qwen_test_automation/ingestion/excel_import.py`
- Test: `qwen-test-automation/tests/ingestion/test_excel_import.py`

**Interfaces:**
- Consumes: `TestScenario` (Foundation/Ingestion models), `PLATFORM_COLUMNS`
  (this task's own rename, from `excel_export`)
- Produces: `read_scenarios_from_excel(path: str) -> list[TestScenario]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ingestion/test_excel_import.py
from qwen_test_automation.models import TestScenario
from qwen_test_automation.ingestion.excel_export import export_scenarios_to_excel
from qwen_test_automation.ingestion.excel_import import read_scenarios_from_excel

def make_scenario(id_="SC-001", applicable_platforms=("WTS", "MWTS")):
    return TestScenario(
        id=id_, feature="Đăng nhập", group="Xác thực", screen="Login",
        title="Đăng nhập với OTP đúng", precondition="Tài khoản tồn tại",
        steps=["Mở trang đăng nhập", "Nhập tài khoản/mật khẩu", "Nhập OTP"],
        expected_result="Vào được trang chủ",
        applicable_platforms=list(applicable_platforms),
    )

def test_read_scenarios_round_trips_through_export(tmp_path):
    out = tmp_path / "testcases.xlsx"
    original = make_scenario()
    export_scenarios_to_excel([original], str(out))
    result = read_scenarios_from_excel(str(out))
    assert len(result) == 1
    assert result[0] == original

def test_read_scenarios_treats_any_non_na_value_as_applicable(tmp_path, monkeypatch=None):
    import openpyxl
    out = tmp_path / "testcases.xlsx"
    export_scenarios_to_excel([make_scenario(applicable_platforms=("WTS",))], str(out))
    wb = openpyxl.load_workbook(str(out))
    ws = wb["Test cases"]
    # QC hand-edits the WTS cell from "Not run" to "Pass" after a manual run
    ws.cell(row=2, column=9).value = "Pass"  # column 9 = WTS
    wb.save(str(out))

    result = read_scenarios_from_excel(str(out))
    assert result[0].applicable_platforms == ["WTS"]

def test_read_scenarios_handles_empty_steps_cell(tmp_path):
    import openpyxl
    out = tmp_path / "testcases.xlsx"
    export_scenarios_to_excel([make_scenario()], str(out))
    wb = openpyxl.load_workbook(str(out))
    ws = wb["Test cases"]
    ws.cell(row=2, column=7).value = None  # column 7 = Bước thực hiện
    wb.save(str(out))

    result = read_scenarios_from_excel(str(out))
    assert result[0].steps == []

def test_read_scenarios_from_header_only_file_returns_empty_list(tmp_path):
    out = tmp_path / "empty.xlsx"
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Test cases"
    ws.append(["Tính năng", "ID", "Nhóm", "Màn hình/module", "Tiêu đề",
               "Tiền điều kiện", "Bước thực hiện", "Kết quả mong đợi",
               "WTS", "MWTS", "MTS-Android", "MTS-iOS", "Bug ID", "Ghi chú"])
    wb.save(str(out))

    assert read_scenarios_from_excel(str(out)) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ingestion/test_excel_import.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Rename `_PLATFORM_COLUMNS` to `PLATFORM_COLUMNS` in `excel_export.py`**

Plain rename, both the definition and its two uses in that file. No
behavior change — existing `test_excel_export.py` tests must still pass
unmodified.

- [ ] **Step 4: Implement `excel_import.py`**

Load the workbook, read sheet `"Test cases"`, build a header→index map
from row 1. For each subsequent row, build a `dict` of header name →
cell value. Parse `"Bước thực hiện"` by splitting on `"\n"`, stripping a
leading `r"^\d+\.\s*"` numeric prefix from each non-empty line (use
`re.sub`); `None`/empty cell → `steps=[]`. `applicable_platforms` is
`[p for p in PLATFORM_COLUMNS if row_values.get(p) not in (None, "N/A")]`.
Build one `TestScenario` per row directly from the mapped values.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ingestion/test_excel_import.py tests/ingestion/test_excel_export.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/ingestion/excel_export.py qwen-test-automation/qwen_test_automation/ingestion/excel_import.py qwen-test-automation/tests/ingestion/test_excel_import.py
git commit -m "feat: add Excel readback into TestScenario"
```

---

### Task 2: `generate-script` and `run-tests` CLI subcommands

**Files:**
- Modify: `qwen-test-automation/cli.py`
- Test: `qwen-test-automation/tests/test_cli.py`

**Interfaces:**
- Consumes: `read_scenarios_from_excel` (Task 1), `to_testcase`
  (Foundation/Ingestion `models`), `ensure_script_generated`/
  `run_web_testcase`/`HostNotAllowedError` (Web Runner), `OllamaClient`
  (Foundation), `load_credentials`/`load_allowed_hosts` (Foundation
  `config`), `init_db` (Foundation `history.db`)
- Produces: `_generate_scripts(scenarios, scripts_dir, allowed_hosts, client, model, supported_platforms=("WTS", "MWTS")) -> list[tuple[str, str]]`
  (one `(testcase_id, script_path)` per generated-or-existing script;
  silently skips any platform not in `supported_platforms` — "silently"
  meaning it does not call Qwen for it, but see `_run_tests` below for
  how skips are surfaced to the user);
  `_run_tests(scenarios, url, allowed_hosts, scripts_dir, conn, credentials=None, account=None, timeout=60, supported_platforms=("WTS", "MWTS")) -> list[tuple[str, str]]`
  (one `(testcase_id, status)` per applicable platform; status is one of
  `"pass"`, `"fail"`, `"pending_claude_review"`, `"blocked"`, or
  `"skipped_unsupported_platform"`; propagates `HostNotAllowedError`
  uncaught from the very first call if `url`'s host isn't allowed, since
  every subsequent call would fail identically)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
import pytest
from qwen_test_automation.models import TestScenario
from qwen_test_automation.history.db import init_db
from qwen_test_automation.runner.script_store import save_script, load_script
from qwen_test_automation.runner.safety_gate import HostNotAllowedError
from cli import _generate_scripts, _run_tests

ALLOWED = {"uat.example.internal"}
URL = "https://uat.example.internal"

class FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text
    def generate(self, model, prompt, images=None):
        return self.response_text

def make_scenario(id_="SC-001", applicable_platforms=("WTS", "MWTS")):
    return TestScenario(
        id=id_, feature="Đăng nhập", group="Xác thực", screen="Login",
        title="Đăng nhập với OTP đúng", precondition="Tài khoản tồn tại",
        steps=["Mở trang đăng nhập", "Nhập OTP"],
        expected_result="Vào được trang chủ",
        applicable_platforms=list(applicable_platforms),
    )

def test_generate_scripts_writes_one_script_per_applicable_web_platform(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = FakeClient("import sys\nsys.exit(0)\n")
    results = _generate_scripts([make_scenario()], scripts_dir, ALLOWED, client, "m")
    ids = [r[0] for r in results]
    assert ids == ["SC-001-WTS", "SC-001-MWTS"]
    assert load_script("SC-001-WTS", scripts_dir) is not None
    assert load_script("SC-001-MWTS", scripts_dir) is not None

def test_generate_scripts_skips_mobile_platforms(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = FakeClient("import sys\nsys.exit(0)\n")
    scenario = make_scenario(applicable_platforms=("WTS", "MTS-Android"))
    results = _generate_scripts([scenario], scripts_dir, ALLOWED, client, "m")
    assert [r[0] for r in results] == ["SC-001-WTS"]

def test_run_tests_runs_each_applicable_web_platform(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    save_script("SC-001-WTS", "import sys\nsys.exit(0)\n", scripts_dir)
    save_script("SC-001-MWTS", "import sys\nsys.exit(1)\n", scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    results = _run_tests([make_scenario()], URL, ALLOWED, scripts_dir, conn)
    assert ("SC-001-WTS", "pass") in results
    assert ("SC-001-MWTS", "pending_claude_review") in results

def test_run_tests_records_skip_for_mobile_platform(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    conn = init_db(str(tmp_path / "h.db"))
    scenario = make_scenario(applicable_platforms=("MTS-Android",))
    results = _run_tests([scenario], URL, ALLOWED, scripts_dir, conn)
    assert results == [("SC-001-MTS-Android", "skipped_unsupported_platform")]

def test_run_tests_raises_immediately_on_disallowed_host(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    conn = init_db(str(tmp_path / "h.db"))
    with pytest.raises(HostNotAllowedError):
        _run_tests([make_scenario()], "https://prod.evil.com", ALLOWED, scripts_dir, conn)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL (module not found / `ImportError: cannot import name '_generate_scripts'`)

- [ ] **Step 3: Implement `_generate_scripts` and `_run_tests` in `cli.py`**

```python
def _generate_scripts(scenarios, scripts_dir, allowed_hosts, client, model, supported_platforms=("WTS", "MWTS")):
    results = []
    for scenario in scenarios:
        for platform in scenario.applicable_platforms:
            if platform not in supported_platforms:
                continue
            testcase = to_testcase(scenario, platform)
            path = ensure_script_generated(testcase, client, model, scripts_dir, allowed_hosts)
            results.append((testcase.id, path))
    return results


def _run_tests(scenarios, url, allowed_hosts, scripts_dir, conn, credentials=None, account=None, timeout=60, supported_platforms=("WTS", "MWTS")):
    results = []
    for scenario in scenarios:
        for platform in scenario.applicable_platforms:
            testcase = to_testcase(scenario, platform)
            if platform not in supported_platforms:
                results.append((testcase.id, "skipped_unsupported_platform"))
                continue
            status = run_web_testcase(
                testcase, url, allowed_hosts, scripts_dir, conn,
                credentials=credentials, account=account, timeout=timeout,
            )
            results.append((testcase.id, status))
    return results
```

Add the matching imports at the top of `cli.py`
(`to_testcase` from `qwen_test_automation.models`;
`ensure_script_generated`, `run_web_testcase` from
`qwen_test_automation.runner.web_runner`;
`load_credentials` from `qwen_test_automation.config.credentials`;
`load_allowed_hosts` from `qwen_test_automation.config.host_allowlist`;
`init_db` from `qwen_test_automation.history.db`;
`read_scenarios_from_excel` from
`qwen_test_automation.ingestion.excel_import`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Wire the two subcommands into `main()`**

Add subparser `generate-script` with arguments `testcases_xlsx`,
`--scripts-dir` (default `"scripts"`), `--host-allowlist` (default
`"config_local/host_allowlist.json"`), `--text-model` (default
`"qwen2.5-coder:7b"`), `--ollama-url` (default
`"http://localhost:11434"`), `--timeout` (`int`, default `120`). Its
handler: `load_allowed_hosts`, build an `OllamaClient`,
`read_scenarios_from_excel`, call `_generate_scripts`, then print one
line per `(testcase_id, path)` ("Generated {path} for {testcase_id} —
review before running") and a final count.

Add subparser `run-tests` with arguments `testcases_xlsx`,
`--scripts-dir` (default `"scripts"`), `--host-allowlist` (default
`"config_local/host_allowlist.json"`), `--credentials` (default
`"config_local/credentials.json"`), `--url` (required), `--account`
(default `None`), `--history-db` (default `"history.db"`), `--timeout`
(`int`, default `60`). Its handler: `load_allowed_hosts`,
`load_credentials` only if `--account` was given (else `None`),
`init_db`, `read_scenarios_from_excel`, then call `_run_tests` inside
`try/except HostNotAllowedError as e: print(f"Lỗi: {e}"); return` (so a
bad `--url` stops the command with one clear message instead of a raw
traceback), otherwise print one line per `(testcase_id, status)` and a
final count per status value.

- [ ] **Step 6: Manual verification**

From `qwen-test-automation/`:
```bash
.venv/bin/python cli.py generate-script --help
.venv/bin/python cli.py run-tests --help
```
Expected: both print usage with the arguments above, no traceback.

- [ ] **Step 7: Commit**

```bash
git add qwen-test-automation/cli.py qwen-test-automation/tests/test_cli.py
git commit -m "feat: add generate-script and run-tests CLI subcommands"
```
