# Qwen Automation Reporting + Pipeline CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the user the two remaining pieces they asked for: a final
Pass/Fail/Blocked/Not run QC report after a test run, and a single
command that goes from "a doc" to "reviewable testcases + reviewable
scripts" in one shot — while keeping the one deliberate manual
checkpoint (reviewing a script before it ever runs) that the Web Runner's
final review required. Chosen explicitly by the user over a fully
unattended alternative that would have skipped that checkpoint.

**Architecture:** `reporting/final_report.py` reads the same
`TestScenario`s used for a run, looks up each applicable platform's
latest `runs` row via a new `history.db` query, maps the internal status
vocabulary to the QC 5-value one (`pass`→Pass, `fail`→Fail,
`blocked`→Blocked, `pending_claude_review`/no run at all→Not run per
spec §10), and writes a "Test cases" sheet plus a "Bug list" sheet (one
row per confirmed Fail). `cli.py` gains a `prepare-tests` subcommand that
chains `run_ingestion` + `_generate_scripts` (both generation-only, no
execution) into one call, and `run-tests` gains a `--report` option that
writes the final report after running — the one command the user
explicitly runs once they've reviewed the generated scripts.

**Tech Stack:** Same venv, `openpyxl` (already present), stdlib only
otherwise.

**Spec:** [docs/superpowers/specs/2026-11-20-local-qwen-automation-design.md](../specs/2026-11-20-local-qwen-automation-design.md)
(§10 — the 5-value status vocabulary and Bug list sheet this plan
produces; §4/§6/the 2026-11-23 note — the generate/review/execute
separation this plan's `prepare-tests` command must not cross)

## Global Constraints

- `prepare-tests` chỉ sinh testcase + script, không bao giờ chạy gì —
  giữ đúng ranh giới generate/execute đã sửa ở Web Runner.
- Trạng thái trong report cuối chỉ dùng 4 trong 5 giá trị QC cho phép mà
  hệ thống tự động biết: `Pass`, `Fail`, `Blocked`, `Not run` (giá trị
  thứ 5, `N/A`, được giữ nguyên từ cột đã có, không tính lại ở đây).
- Mọi cell ghi vào Excel (kể cả nội dung lỗi) phải ép kiểu string
  (`data_type = "s"`) để tránh bị hiểu nhầm thành công thức, như đã sửa
  ở Ingestion.

## Review Focus

- Testcase chưa từng chạy lần nào (không có row trong `runs`) →
  `get_latest_run` trả `None`, report phải ghi `"Not run"`, không crash.
  (Task 1)
- `pending_claude_review` (đã chạy nhưng chưa xử lý xong) → cũng phải
  map thành `"Not run"` theo đúng spec §10, không phải một nhãn khác.
  (Task 1)
- Nền tảng không áp dụng (đã là `"N/A"` từ lúc ingestion) → report phải
  giữ nguyên `"N/A"`, không tra cứu `history.db` cho nền tảng đó, không
  bị ghi đè thành `"Not run"`. (Task 1)
- Nội dung message lỗi bắt đầu bằng `"="` → không được trở thành công
  thức Excel hỏng khi ghi vào report. (Task 1)
- Danh sách scenario rỗng truyền vào `write_final_report` → phải raise
  lỗi rõ ràng (nhất quán với `export_scenarios_to_excel`), không âm thầm
  tạo ra 1 file report trống vô nghĩa. (Task 1)

---

### Task 1: Final report (Pass/Fail/Blocked/Not run + Bug list)

**Files:**
- Modify: `qwen-test-automation/qwen_test_automation/history/db.py`
  (add `get_latest_run`)
- Modify: `qwen-test-automation/tests/history/test_db.py`
- Create: `qwen-test-automation/qwen_test_automation/reporting/__init__.py`
- Create: `qwen-test-automation/qwen_test_automation/reporting/final_report.py`
- Test: `qwen-test-automation/tests/reporting/test_final_report.py`

**Interfaces:**
- Consumes: `TestScenario`/`to_testcase` (Foundation/Ingestion `models`),
  `PLATFORM_COLUMNS` (Ingestion `excel_export`)
- Produces: `get_latest_run(conn, testcase_id: str) -> dict | None`
  (most recent row of `runs` for that testcase id, or `None`);
  `write_final_report(scenarios: list, conn, out_path: str) -> None`
  (raises `ValueError` if `scenarios` is empty)

- [ ] **Step 1: Write the failing tests**

```python
# tests/history/test_db.py (append)
def test_get_latest_run_returns_none_when_no_run(tmp_path):
    conn = init_db(str(tmp_path / "history.db"))
    insert_testcase(conn, make_testcase())
    assert get_latest_run(conn, "TC-001") is None

def test_get_latest_run_returns_most_recent(tmp_path):
    conn = init_db(str(tmp_path / "history.db"))
    insert_testcase(conn, make_testcase())
    record_run(conn, "TC-001", "pending_claude_review", "locator", "first")
    record_run(conn, "TC-001", "pass", None, "second")
    result = get_latest_run(conn, "TC-001")
    assert result["status"] == "pass"
    assert result["message"] == "second"
```
(add `get_latest_run` to the existing import line from
`qwen_test_automation.history.db`)

```python
# tests/reporting/test_final_report.py
import pytest
import openpyxl
from qwen_test_automation.models import TestScenario, to_testcase
from qwen_test_automation.history.db import init_db, insert_testcase, record_run
from qwen_test_automation.reporting.final_report import write_final_report

def make_scenario(id_="SC-001", applicable_platforms=("WTS",)):
    return TestScenario(
        id=id_, feature="Đăng nhập", group="Xác thực", screen="Login",
        title="Đăng nhập với OTP đúng", precondition="Tài khoản tồn tại",
        steps=["Mở trang đăng nhập", "Nhập OTP"],
        expected_result="Vào được trang chủ",
        applicable_platforms=list(applicable_platforms),
    )

def _row_dict(ws, row_number):
    header = [c.value for c in ws[1]]
    return dict(zip(header, [c.value for c in ws[row_number]]))

def test_write_final_report_maps_pass_status(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    scenario = make_scenario()
    testcase = to_testcase(scenario, "WTS")
    insert_testcase(conn, testcase)
    record_run(conn, testcase.id, "pass", None, "")
    out = tmp_path / "report.xlsx"
    write_final_report([scenario], conn, str(out))
    ws = openpyxl.load_workbook(str(out))["Test cases"]
    assert _row_dict(ws, 2)["WTS"] == "Pass"

def test_write_final_report_never_run_is_not_run(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    out = tmp_path / "report.xlsx"
    write_final_report([make_scenario()], conn, str(out))
    ws = openpyxl.load_workbook(str(out))["Test cases"]
    assert _row_dict(ws, 2)["WTS"] == "Not run"

def test_write_final_report_pending_claude_review_is_not_run(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    scenario = make_scenario()
    testcase = to_testcase(scenario, "WTS")
    insert_testcase(conn, testcase)
    record_run(conn, testcase.id, "pending_claude_review", "locator", "selector not found")
    out = tmp_path / "report.xlsx"
    write_final_report([scenario], conn, str(out))
    ws = openpyxl.load_workbook(str(out))["Test cases"]
    assert _row_dict(ws, 2)["WTS"] == "Not run"

def test_write_final_report_keeps_na_for_inapplicable_platform(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    out = tmp_path / "report.xlsx"
    write_final_report([make_scenario(applicable_platforms=("WTS",))], conn, str(out))
    ws = openpyxl.load_workbook(str(out))["Test cases"]
    assert _row_dict(ws, 2)["MWTS"] == "N/A"

def test_write_final_report_fills_ghi_chu_and_bug_list_for_fail(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    scenario = make_scenario()
    testcase = to_testcase(scenario, "WTS")
    insert_testcase(conn, testcase)
    record_run(conn, testcase.id, "fail", "assertion", "expected Dashboard, got Login")
    out = tmp_path / "report.xlsx"
    write_final_report([scenario], conn, str(out))
    wb = openpyxl.load_workbook(str(out))
    main_row = _row_dict(wb["Test cases"], 2)
    assert main_row["WTS"] == "Fail"
    assert "expected Dashboard" in main_row["Ghi chú"]
    bug_ws = wb["Bug list"]
    bug_ids = [row[0].value for row in bug_ws.iter_rows(min_row=2)]
    assert bug_ids == ["SC-001-WTS"]

def test_write_final_report_does_not_treat_leading_equals_as_formula(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    scenario = make_scenario()
    testcase = to_testcase(scenario, "WTS")
    insert_testcase(conn, testcase)
    record_run(conn, testcase.id, "fail", "assertion", "=> không khớp kết quả")
    out = tmp_path / "report.xlsx"
    write_final_report([scenario], conn, str(out))
    ws = openpyxl.load_workbook(str(out))["Test cases"]
    cell = ws.cell(row=2, column=14)  # Ghi chú is the last column
    assert cell.data_type == "s"

def test_write_final_report_raises_on_empty_scenarios(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    out = tmp_path / "report.xlsx"
    with pytest.raises(ValueError):
        write_final_report([], conn, str(out))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/history/test_db.py tests/reporting/test_final_report.py -v`
Expected: FAIL (module/function not found)

- [ ] **Step 3: Implement `get_latest_run` in `history/db.py`**

```python
def get_latest_run(conn: sqlite3.Connection, testcase_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM runs WHERE testcase_id = ? ORDER BY id DESC LIMIT 1",
        (testcase_id,),
    ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 4: Implement `reporting/final_report.py`**

Status map: `{"pass": "Pass", "fail": "Fail", "blocked": "Blocked", "pending_claude_review": "Not run"}`,
with `"Not run"` also the default when `get_latest_run` returns `None`.
Main sheet header is identical to `excel_export.py`'s (reuse
`PLATFORM_COLUMNS` from there). If `scenarios` is empty, raise
`ValueError("no scenarios to report")`. For each scenario: write the 8
text columns (same `steps` numbering as `excel_export.py`), then for
each of the 4 platform columns — if not in
`scenario.applicable_platforms`, write `"N/A"` and move on without
querying the DB; otherwise look up
`get_latest_run(conn, to_testcase(scenario, platform).id)`, map its
`status` (or `"Not run"` if `None`) into the cell, and if the mapped
status is `"Fail"` or `"Blocked"`, collect `f"{platform}: {run['message']}"`
into that scenario's notes list and (for `"Fail"` only) append a row to
the Bug list sheet's buffer:
`[testcase_id, platform, scenario.feature, scenario.title, "", "", run["message"]]`
(`"Mức độ"` and `"Bug ID"` left blank for a human to fill). After the
platform columns, append an empty `Bug ID` cell and
`"; ".join(notes)` for `Ghi chú`. After every row (both sheets), set
`cell.data_type = "s"` on each cell of that row, exactly as
`excel_export.py` does. Bug list sheet header:
`["Testcase ID", "Nền tảng", "Tính năng", "Tiêu đề", "Mức độ", "Bug ID", "Ghi chú"]`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/history/test_db.py tests/reporting/test_final_report.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/history/db.py qwen-test-automation/tests/history/test_db.py qwen-test-automation/qwen_test_automation/reporting/ qwen-test-automation/tests/reporting/
git commit -m "feat: add final Pass/Fail/Blocked/Not run report with Bug list"
```

---

### Task 2: `prepare-tests` CLI command + `run-tests --report`

**Files:**
- Modify: `qwen-test-automation/cli.py`
- Modify: `qwen-test-automation/tests/test_cli.py`

**Interfaces:**
- Consumes: `run_ingestion` (Ingestion `pipeline`), `_generate_scripts`
  (this file, already present), `write_final_report` (Task 1)
- Produces: `_default_report_path(testcases_xlsx: str) -> str` (replaces
  the extension with `_report` + the same extension, e.g.
  `"out/ra.xlsx"` → `"out/ra_report.xlsx"`); `_print_generate_results(results)`
  (factored out of the existing `generate-script` handler so
  `prepare-tests` can reuse the same per-testcase print formatting
  without duplicating it)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py (append)
from cli import _default_report_path

def test_default_report_path_inserts_suffix_before_extension():
    assert _default_report_path("out/ra.xlsx") == "out/ra_report.xlsx"
    assert _default_report_path("ra.xlsx") == "ra_report.xlsx"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli.py -v -k default_report_path`
Expected: FAIL (`ImportError: cannot import name '_default_report_path'`)

- [ ] **Step 3: Implement `_default_report_path` and `_print_generate_results` in `cli.py`**

```python
import os

def _default_report_path(testcases_xlsx):
    base, ext = os.path.splitext(testcases_xlsx)
    return f"{base}_report{ext}"


def _print_generate_results(results):
    for testcase_id, result in results:
        if result == "skipped_unsupported_platform":
            print(f"{testcase_id}: bỏ qua (nền tảng mobile chưa được CLI này hỗ trợ)")
        elif isinstance(result, str) and result.startswith("error:"):
            print(f"{testcase_id}: {result}")
        else:
            print(f"Generated {result} for {testcase_id} — review before running")
```
Replace the inline printing loop inside the existing `generate-script`
handler with a call to `_print_generate_results(results)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli.py -v -k default_report_path`
Expected: PASS

- [ ] **Step 5: Add the `prepare-tests` subparser and handler**

Arguments: `doc_path`, `out_path` (positional, same as
`generate-scenarios`), `--scripts-dir` (default `"scripts"`),
`--host-allowlist` (default `"config_local/host_allowlist.json"`),
`--text-model` (default `"qwen2.5:7b"`), `--vision-model` (default
`"qwen2.5vl:7b"`), `--script-model` (default `"qwen2.5-coder:7b"`),
`--ollama-url` (default `"http://localhost:11434"`), `--timeout`
(`int`, default `120`). Handler: `_require_nonempty_allowlist` (print
`"Lỗi: ..."` and return on `ValueError`, same pattern as the other two
handlers), build one `OllamaClient`, call `run_ingestion(doc_path,
out_path, client, text_model=..., vision_model=...)` (prints `"Đã sinh
{n} testcase vào {out_path}"`), then `_generate_scripts(scenarios,
scripts_dir, allowed_hosts, client, script_model)`, print its results
via `_print_generate_results`, and finish with:
```
print(f"\nĐã sinh {len(results)} script vào {scripts_dir}/.")
print(f"Review {out_path} và các file trong {scripts_dir}/ trước khi chạy.")
print(f"Khi sẵn sàng: python cli.py run-tests {out_path} --url <host> --account <account>")
```
Never calls `run_script`/`run_web_testcase` — this command only
generates.

- [ ] **Step 6: Add `--report` to `run-tests` and write the final report**

Add `runtests.add_argument("--report", default=None, help="Đường dẫn
report cuối (mặc định: <file input>_report.xlsx)")`. In the handler,
after the existing per-testcase print loop and before the final
`"Tổng kết"` line, compute `report_path = args.report or
_default_report_path(args.testcases_xlsx)`, call
`write_final_report(scenarios, conn, report_path)`, and print
`f"Report: {report_path}"`.

- [ ] **Step 7: Manual verification**

From `qwen-test-automation/`:
```bash
.venv/bin/python cli.py prepare-tests --help
.venv/bin/python cli.py run-tests --help
```
Expected: `prepare-tests --help` lists the arguments above; `run-tests
--help` now also lists `--report`. No traceback.

- [ ] **Step 8: Commit**

```bash
git add qwen-test-automation/cli.py qwen-test-automation/tests/test_cli.py
git commit -m "feat: add prepare-tests command and run-tests --report"
```
