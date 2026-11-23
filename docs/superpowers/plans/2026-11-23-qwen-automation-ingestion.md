# Qwen Automation Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user drop a document (PDF, plain-text/Redmine export, or
image) in and get back a QC-format testcase Excel file — the "docs in,
testcase Excel out" half of the tool, built on the Foundation layer
(`OllamaClient`, `TestCase`, `VALID_PLATFORMS`).

**Architecture:** A new `TestScenario` model (one row per test idea, many
platforms) sits above the Foundation's per-platform `TestCase`, with a
`to_testcase(scenario, platform)` derivation for the later runner plan.
`ingestion/doc_reader.py` turns a file path into text + base64 images
(PyMuPDF, no external system dependency); `ingestion/scenario_generator.py`
calls Qwen (via the existing `OllamaClient`) with a QC-voice prompt to
produce `TestScenario` objects; `ingestion/excel_export.py` writes them to
the QC "Test cases" sheet; `ingestion/pipeline.py` + a `cli.py` entry point
wire the three together into one command.

**Tech Stack:** Same Python venv as Foundation (`qwen-test-automation/.venv`,
Python 3.9.6 — see Foundation ledger). New dependencies: `PyMuPDF` (PDF
text + page-image extraction, pure wheel, no Poppler/system install) and
`openpyxl` (Excel output).

**Spec:** [docs/superpowers/specs/2026-11-20-local-qwen-automation-design.md](../specs/2026-11-20-local-qwen-automation-design.md)
(see §10, added 2026-11-23, for the QC format/voice rules this plan
implements, and the `TestScenario`/`TestCase` split it resolves)

## Global Constraints

- Mọi testcase/ghi chú sinh ra phải theo giọng văn QC trung tính (spec §10):
  không tự xưng, không nhãn quy trình/công cụ ("QC xác nhận", "Claude soi"...).
- Cột nền tảng trong Excel ở giai đoạn này chỉ nhận giá trị `"Not run"` (áp
  dụng) hoặc `"N/A"` (không áp dụng) — chưa có lần chạy nào.
- Testcase (scenario) không áp dụng cho bất kỳ nền tảng nào (N/A toàn bộ)
  phải bị loại khỏi report, không xuất ra dòng N/A-toàn-bộ (spec §10).
- Redmine ở giai đoạn này chỉ nhận nội dung đã export/paste ra file
  `.txt`/`.md` — chưa gọi API thật (spec §3, §9: chưa có token).
- Không tự động chạy test từ scenario vừa sinh — chỉ xuất Excel để người
  dùng review trước (spec §4 anti-goal).

## Review Focus

- Qwen trả scenario thiếu field, hoặc `applicable_platforms` rỗng/chứa giá
  trị không nằm trong `VALID_PLATFORMS` → `generate_scenarios` phải raise
  lỗi rõ ràng, không âm thầm bỏ qua hay trả scenario sai. (Task 3)
- File PDF hỏng/không đọc được text → `read_input` phải raise lỗi rõ ràng,
  không trả text rỗng mà coi như thành công. (Task 2)
- File đầu vào không phải `.pdf`/`.txt`/`.md`/`.png`/`.jpg`/`.jpeg` →
  `read_input` phải raise `ValueError` ngay, không âm thầm coi là text rỗng.
  (Task 2)
- Xuất Excel với danh sách scenario rỗng → phải raise lỗi rõ ràng (một file
  Excel không có testcase nào gần như luôn là dấu hiệu lỗi ở bước trước, im
  lặng tạo file rỗng sẽ che mất lỗi đó). (Task 4)
- Scenario không áp dụng cho nền tảng nào (`applicable_platforms == []`)
  phải bị loại khỏi Excel, không xuất dòng toàn N/A. (Task 4)

---

### Task 1: `TestScenario` model + `to_testcase` derivation

**Files:**
- Modify: `qwen-test-automation/qwen_test_automation/models.py`
- Modify: `qwen-test-automation/tests/test_models.py`

**Interfaces:**
- Consumes: `TestCase`, `VALID_PLATFORMS` (already in this file)
- Produces: `TestScenario` dataclass — `id: str`, `feature: str`,
  `group: str`, `screen: str`, `title: str`, `precondition: str`,
  `steps: list[str]`, `expected_result: str`,
  `applicable_platforms: list[str]`. `TestScenario.to_dict() -> dict`,
  `TestScenario.from_dict(data: dict) -> TestScenario`.
  `to_testcase(scenario: TestScenario, platform: str) -> TestCase` (raises
  `ValueError` if `platform not in scenario.applicable_platforms`; result's
  `id` is `f"{scenario.id}-{platform}"`, `feature` is `scenario.title`,
  `precondition`/`steps`/`expected_result` copied through).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_models.py (append)
from qwen_test_automation.models import TestScenario, to_testcase

def make_scenario(applicable_platforms=("WTS", "MWTS")):
    return TestScenario(
        id="SC-001", feature="Đăng nhập", group="Xác thực", screen="Login",
        title="Đăng nhập với OTP đúng",
        precondition="Tài khoản tồn tại, đã đăng ký OTP",
        steps=["Mở trang đăng nhập", "Nhập tài khoản/mật khẩu", "Nhập OTP"],
        expected_result="Vào được trang chủ sau khi xác thực",
        applicable_platforms=list(applicable_platforms),
    )

def test_scenario_round_trips_through_dict():
    sc = make_scenario()
    assert TestScenario.from_dict(sc.to_dict()) == sc

def test_to_testcase_derives_platform_specific_testcase():
    sc = make_scenario(("WTS", "MWTS"))
    tc = to_testcase(sc, "WTS")
    assert tc.id == "SC-001-WTS"
    assert tc.feature == "Đăng nhập với OTP đúng"
    assert tc.platform == "WTS"
    assert tc.steps == sc.steps
    assert tc.precondition == sc.precondition
    assert tc.expected_result == sc.expected_result

def test_to_testcase_raises_when_platform_not_applicable():
    sc = make_scenario(("WTS",))
    with pytest.raises(ValueError):
        to_testcase(sc, "MTS-Android")
```

(`tests/test_models.py` currently has no `import pytest` — add
`import pytest` at the top alongside the existing import.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL with "cannot import name 'TestScenario'"

- [ ] **Step 3: Implement `TestScenario` and `to_testcase` in `models.py`**

`TestScenario` is a `@dataclass`, same `to_dict`/`from_dict` pattern as
`TestCase` (direct field mapping; `steps` and `applicable_platforms` stay
lists). `to_testcase` raises
`ValueError(f"platform {platform} not applicable to scenario {scenario.id}")`
before constructing the `TestCase`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/models.py qwen-test-automation/tests/test_models.py
git commit -m "feat: add TestScenario model and to_testcase derivation"
```

---

### Task 2: Document reader (PDF / text / image)

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/ingestion/__init__.py`
- Create: `qwen-test-automation/qwen_test_automation/ingestion/doc_reader.py`
- Modify: `qwen-test-automation/requirements.txt` (add `PyMuPDF`)
- Test: `qwen-test-automation/tests/ingestion/test_doc_reader.py`

**Interfaces:**
- Consumes: none
- Produces: `UnsupportedDocumentError(Exception)`; `DocumentReadError(Exception)`;
  `read_input(path: str) -> dict` returning `{"text": str, "images": list[str]}`
  (`images` are base64-encoded PNG strings). `.pdf` → extract text per page
  (joined with blank lines) plus each page rendered to a base64 PNG, or
  raise `DocumentReadError` if the file cannot be parsed as a PDF at all.
  `.txt`/`.md` → file content as `text`, `images=[]`. `.png`/`.jpg`/`.jpeg` →
  `text=""`, `images=[<base64 of the file>]`. Any other extension raises
  `UnsupportedDocumentError`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ingestion/test_doc_reader.py
import base64
import pytest
from qwen_test_automation.ingestion.doc_reader import (
    read_input, UnsupportedDocumentError, DocumentReadError,
)

def test_read_input_text_file(tmp_path):
    p = tmp_path / "ticket.txt"
    p.write_text("Yêu cầu: cho phép đăng nhập bằng OTP")
    result = read_input(str(p))
    assert result["text"] == "Yêu cầu: cho phép đăng nhập bằng OTP"
    assert result["images"] == []

def test_read_input_markdown_file(tmp_path):
    p = tmp_path / "ticket.md"
    p.write_text("# Ticket\n\nNoi dung")
    result = read_input(str(p))
    assert "Noi dung" in result["text"]
    assert result["images"] == []

def test_read_input_image_file(tmp_path):
    p = tmp_path / "screenshot.png"
    raw = b"\x89PNG\r\n\x1a\nfake-but-nonempty-bytes"
    p.write_bytes(raw)
    result = read_input(str(p))
    assert result["text"] == ""
    assert result["images"] == [base64.b64encode(raw).decode()]

def test_read_input_unsupported_extension_raises(tmp_path):
    p = tmp_path / "ticket.docx"
    p.write_text("irrelevant")
    with pytest.raises(UnsupportedDocumentError):
        read_input(str(p))

def test_read_input_pdf_extracts_text_and_page_images(tmp_path):
    import fitz  # PyMuPDF
    p = tmp_path / "ticket.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Yeu cau dang nhap OTP")
    doc.save(str(p))
    doc.close()

    result = read_input(str(p))
    assert "Yeu cau dang nhap OTP" in result["text"]
    assert len(result["images"]) == 1
    assert isinstance(result["images"][0], str) and len(result["images"][0]) > 0

def test_read_input_corrupt_pdf_raises_clear_error(tmp_path):
    p = tmp_path / "corrupt.pdf"
    p.write_bytes(b"%PDF-1.4 this is not a real pdf body")
    with pytest.raises(DocumentReadError, match="could not"):
        read_input(str(p))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ingestion/test_doc_reader.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Add `PyMuPDF` to `requirements.txt` and implement `doc_reader.py`**

Append `PyMuPDF>=1.24` to `qwen-test-automation/requirements.txt`, then
`.venv/bin/pip install -r requirements.txt`.

`read_input` dispatches on `pathlib.Path(path).suffix.lower()`. For `.pdf`,
open with `fitz.open(path)` inside `try/except Exception as e: raise
DocumentReadError(f"could not read PDF: {path} ({e})") from e`; for each
page, `page.get_text()` (joined with `"\n\n"` across pages) and
`page.get_pixmap().tobytes("png")` → base64 per page, collected into
`images`. For `.txt`/`.md`, read the file as UTF-8 text. For
`.png`/`.jpg`/`.jpeg`, read the file as bytes and base64-encode. Any other
suffix raises `UnsupportedDocumentError(f"unsupported document type: {path}")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ingestion/test_doc_reader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/ingestion/__init__.py qwen-test-automation/qwen_test_automation/ingestion/doc_reader.py qwen-test-automation/requirements.txt qwen-test-automation/tests/ingestion/test_doc_reader.py
git commit -m "feat: add document reader for PDF/text/image ingestion"
```

---

### Task 3: Scenario generator (QC voice)

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/ingestion/scenario_generator.py`
- Test: `qwen-test-automation/tests/ingestion/test_scenario_generator.py`

**Interfaces:**
- Consumes: `OllamaClient` (Foundation), `TestScenario`/`VALID_PLATFORMS`
  (Task 1 / Foundation)
- Produces: `ScenarioParseError(Exception)`;
  `generate_scenarios(doc_text: str, client, model: str, images: list[str] | None = None) -> list[TestScenario]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ingestion/test_scenario_generator.py
import json
import pytest
from qwen_test_automation.ingestion.scenario_generator import (
    generate_scenarios, ScenarioParseError,
)

class FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text
        self.last_prompt = None
    def generate(self, model, prompt, images=None):
        self.last_prompt = prompt
        return self.response_text

def _valid_scenario_json():
    return json.dumps([{
        "id": "SC-001", "feature": "Đăng nhập", "group": "Xác thực",
        "screen": "Login", "title": "Đăng nhập với OTP đúng",
        "precondition": "Tài khoản tồn tại",
        "steps": ["Mở trang đăng nhập", "Nhập OTP"],
        "expected_result": "Vào được trang chủ",
        "applicable_platforms": ["WTS", "MWTS"],
    }])

def test_generate_scenarios_parses_valid_json_array():
    client = FakeClient(_valid_scenario_json())
    result = generate_scenarios("doc text", client=client, model="qwen2.5:7b")
    assert len(result) == 1
    assert result[0].id == "SC-001"
    assert result[0].applicable_platforms == ["WTS", "MWTS"]

def test_generate_scenarios_prompt_requests_qc_voice():
    client = FakeClient(_valid_scenario_json())
    generate_scenarios("doc text", client=client, model="qwen2.5:7b")
    assert "không" in client.last_prompt  # prompt carries the QC-voice negative instructions

def test_generate_scenarios_raises_on_missing_field():
    payload = json.dumps([{
        "id": "SC-001", "feature": "Đăng nhập", "group": "Xác thực",
        "screen": "Login", "title": "Đăng nhập với OTP đúng",
        "precondition": "Tài khoản tồn tại",
        "expected_result": "Vào được trang chủ",
        "applicable_platforms": ["WTS"],
        # "steps" missing
    }])
    client = FakeClient(payload)
    with pytest.raises(ScenarioParseError, match="steps"):
        generate_scenarios("doc text", client=client, model="qwen2.5:7b")

def test_generate_scenarios_raises_on_empty_applicable_platforms():
    payload = json.dumps([{
        "id": "SC-001", "feature": "Đăng nhập", "group": "Xác thực",
        "screen": "Login", "title": "Đăng nhập với OTP đúng",
        "precondition": "Tài khoản tồn tại", "steps": ["Mở trang"],
        "expected_result": "Vào được trang chủ",
        "applicable_platforms": [],
    }])
    client = FakeClient(payload)
    with pytest.raises(ScenarioParseError, match="applicable_platforms"):
        generate_scenarios("doc text", client=client, model="qwen2.5:7b")

def test_generate_scenarios_raises_on_invalid_platform_in_list():
    payload = json.dumps([{
        "id": "SC-001", "feature": "Đăng nhập", "group": "Xác thực",
        "screen": "Login", "title": "Đăng nhập với OTP đúng",
        "precondition": "Tài khoản tồn tại", "steps": ["Mở trang"],
        "expected_result": "Vào được trang chủ",
        "applicable_platforms": ["WTS", "NotAPlatform"],
    }])
    client = FakeClient(payload)
    with pytest.raises(ScenarioParseError, match="applicable_platforms"):
        generate_scenarios("doc text", client=client, model="qwen2.5:7b")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ingestion/test_scenario_generator.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `scenario_generator.py`**

Prompt template instructs Qwen (in Vietnamese) to act as a QC test writer:
output only a JSON array of objects with fields `id, feature, group, screen,
title, precondition, steps, expected_result, applicable_platforms` (listing
`VALID_PLATFORMS` as the allowed values), and explicitly states the voice
rules from spec §10 — neutral QC voice, no first person, no process/tool
labels such as "QC xác nhận" or "Claude" (the prompt must contain the word
"không" somewhere in these negative instructions, which
`test_generate_scenarios_prompt_requests_qc_voice` checks for). Call
`client.generate(model=model, prompt=prompt, images=images)`, `json.loads`
the result (raise `ScenarioParseError` on decode failure or non-list,
mirroring Foundation's `testcase_generator.py` pattern). For each item:
check it's a `dict` with all required fields present (raise
`ScenarioParseError` naming the missing field(s), e.g. `"steps"`); check
`applicable_platforms` is a non-empty list where every element is in
`VALID_PLATFORMS` (raise `ScenarioParseError` mentioning
`"applicable_platforms"` for either failure); then build via
`TestScenario.from_dict(item)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ingestion/test_scenario_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/ingestion/scenario_generator.py qwen-test-automation/tests/ingestion/test_scenario_generator.py
git commit -m "feat: add QC-voice scenario generator over Ollama"
```

---

### Task 4: QC Excel export

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/ingestion/excel_export.py`
- Modify: `qwen-test-automation/requirements.txt` (add `openpyxl`)
- Test: `qwen-test-automation/tests/ingestion/test_excel_export.py`

**Interfaces:**
- Consumes: `TestScenario`, `VALID_PLATFORMS` (Task 1 / Foundation)
- Produces: `export_scenarios_to_excel(scenarios: list, path: str) -> None`
  (raises `ValueError` if `scenarios` is empty, or if every scenario is
  dropped for having no applicable platform)

- [ ] **Step 1: Write the failing tests**

```python
# tests/ingestion/test_excel_export.py
import pytest
import openpyxl
from qwen_test_automation.models import TestScenario
from qwen_test_automation.ingestion.excel_export import export_scenarios_to_excel

def make_scenario(id_="SC-001", applicable_platforms=("WTS", "MWTS")):
    return TestScenario(
        id=id_, feature="Đăng nhập", group="Xác thực", screen="Login",
        title="Đăng nhập với OTP đúng", precondition="Tài khoản tồn tại",
        steps=["Mở trang đăng nhập", "Nhập OTP"],
        expected_result="Vào được trang chủ",
        applicable_platforms=list(applicable_platforms),
    )

def test_export_writes_expected_header_and_row(tmp_path):
    out = tmp_path / "testcases.xlsx"
    export_scenarios_to_excel([make_scenario()], str(out))
    wb = openpyxl.load_workbook(str(out))
    ws = wb["Test cases"]
    header = [c.value for c in ws[1]]
    assert header == [
        "Tính năng", "ID", "Nhóm", "Màn hình/module", "Tiêu đề",
        "Tiền điều kiện", "Bước thực hiện", "Kết quả mong đợi",
        "WTS", "MWTS", "MTS-Android", "MTS-iOS", "Bug ID", "Ghi chú",
    ]
    row = [c.value for c in ws[2]]
    assert row[1] == "SC-001"
    assert row[8] == "Not run"   # WTS: applicable
    assert row[10] == "N/A"      # MTS-Android: not applicable

def test_export_drops_scenario_with_no_applicable_platform(tmp_path):
    out = tmp_path / "testcases.xlsx"
    only_na = make_scenario(id_="SC-002", applicable_platforms=())
    export_scenarios_to_excel([make_scenario(), only_na], str(out))
    wb = openpyxl.load_workbook(str(out))
    ws = wb["Test cases"]
    ids = [row[1].value for row in ws.iter_rows(min_row=2)]
    assert "SC-002" not in ids
    assert "SC-001" in ids

def test_export_raises_on_empty_scenario_list(tmp_path):
    out = tmp_path / "testcases.xlsx"
    with pytest.raises(ValueError):
        export_scenarios_to_excel([], str(out))

def test_export_raises_when_all_scenarios_dropped(tmp_path):
    out = tmp_path / "testcases.xlsx"
    only_na = make_scenario(applicable_platforms=())
    with pytest.raises(ValueError):
        export_scenarios_to_excel([only_na], str(out))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ingestion/test_excel_export.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Add `openpyxl` to `requirements.txt` and implement `excel_export.py`**

Append `openpyxl>=3.1` to `requirements.txt`, then
`.venv/bin/pip install -r requirements.txt`.

Column order is fixed:
`["Tính năng", "ID", "Nhóm", "Màn hình/module", "Tiêu đề", "Tiền điều kiện", "Bước thực hiện", "Kết quả mong đợi"] + sorted(VALID_PLATFORMS) + ["Bug ID", "Ghi chú"]`
— note `sorted(VALID_PLATFORMS)` must produce `["MTS-Android", "MTS-iOS", "MWTS", "WTS"]`
alphabetically; since the test above expects `WTS, MWTS, MTS-Android, MTS-iOS`
order, hard-code the platform column order as
`["WTS", "MWTS", "MTS-Android", "MTS-iOS"]` (matching `VALID_PLATFORMS`'s
members, not alphabetically sorted) instead of sorting.

If `scenarios` is empty, raise
`ValueError("no scenarios to export")` before any filtering. Filter out
scenarios whose `applicable_platforms` is empty; if that leaves nothing,
raise `ValueError("all scenarios were dropped: none apply to any platform")`.
For each remaining scenario, write one row: the 8 text fields, then for
each of the 4 platform columns `"Not run"` if that platform is in
`scenario.applicable_platforms` else `"N/A"`, then empty `Bug ID`/`Ghi chú`.
`steps` is joined as `"\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))`.
Use `openpyxl.Workbook()`, rename the active sheet to `"Test cases"`, write
the header row then one row per kept scenario, `wb.save(path)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ingestion/test_excel_export.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/ingestion/excel_export.py qwen-test-automation/requirements.txt qwen-test-automation/tests/ingestion/test_excel_export.py
git commit -m "feat: add QC-format Excel export for test scenarios"
```

---

### Task 5: Ingestion pipeline + CLI

**Files:**
- Create: `qwen-test-automation/qwen_test_automation/ingestion/pipeline.py`
- Create: `qwen-test-automation/cli.py`
- Test: `qwen-test-automation/tests/ingestion/test_pipeline.py`

**Interfaces:**
- Consumes: `read_input` (Task 2), `generate_scenarios` (Task 3),
  `export_scenarios_to_excel` (Task 4), `OllamaClient` (Foundation)
- Produces: `run_ingestion(doc_path: str, out_path: str, client, text_model: str, vision_model: str) -> list`
  (returns the list of `TestScenario` it exported; picks `vision_model` when
  `read_input` returns non-empty `images`, else `text_model`)

- [ ] **Step 1: Write the failing test**

```python
# tests/ingestion/test_pipeline.py
import json
import openpyxl
from qwen_test_automation.ingestion.pipeline import run_ingestion

class FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text
        self.used_model = None
    def generate(self, model, prompt, images=None):
        self.used_model = model
        return self.response_text

def _scenario_json():
    return json.dumps([{
        "id": "SC-001", "feature": "Đăng nhập", "group": "Xác thực",
        "screen": "Login", "title": "Đăng nhập với OTP đúng",
        "precondition": "Tài khoản tồn tại", "steps": ["Mở trang"],
        "expected_result": "Vào được trang chủ",
        "applicable_platforms": ["WTS"],
    }])

def test_run_ingestion_text_file_uses_text_model(tmp_path):
    doc = tmp_path / "ticket.txt"
    doc.write_text("Yêu cầu đăng nhập OTP")
    out = tmp_path / "testcases.xlsx"
    client = FakeClient(_scenario_json())

    result = run_ingestion(str(doc), str(out), client=client, text_model="text-m", vision_model="vision-m")

    assert client.used_model == "text-m"
    assert len(result) == 1
    wb = openpyxl.load_workbook(str(out))
    assert "Test cases" in wb.sheetnames

def test_run_ingestion_image_file_uses_vision_model(tmp_path):
    doc = tmp_path / "shot.png"
    doc.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    out = tmp_path / "testcases.xlsx"
    client = FakeClient(_scenario_json())

    run_ingestion(str(doc), str(out), client=client, text_model="text-m", vision_model="vision-m")

    assert client.used_model == "vision-m"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/ingestion/test_pipeline.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `pipeline.py`**

```python
def run_ingestion(doc_path, out_path, client, text_model, vision_model):
    parsed = read_input(doc_path)
    model = vision_model if parsed["images"] else text_model
    scenarios = generate_scenarios(
        parsed["text"], client=client, model=model, images=parsed["images"] or None
    )
    export_scenarios_to_excel(scenarios, out_path)
    return scenarios
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/ingestion/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Implement the CLI entry point `cli.py`**

`argparse`-based script at `qwen-test-automation/cli.py` with one
subcommand:
```
python cli.py generate-scenarios <doc_path> <out_path> [--text-model qwen2.5:7b] [--vision-model qwen2.5vl:7b] [--ollama-url http://localhost:11434]
```
It constructs an `OllamaClient(base_url=ollama_url)` and calls
`run_ingestion(doc_path, out_path, client, text_model, vision_model)`,
then prints `f"Wrote {len(scenarios)} scenario(s) to {out_path}"`. No test
required for `cli.py` itself (thin argument-parsing wrapper over
`run_ingestion`, already covered); this step is manual verification only —
run it once by hand against a real `.txt` file once Ollama is installed and
confirm the printed count and that the `.xlsx` opens.

- [ ] **Step 6: Commit**

```bash
git add qwen-test-automation/qwen_test_automation/ingestion/pipeline.py qwen-test-automation/cli.py qwen-test-automation/tests/ingestion/test_pipeline.py
git commit -m "feat: wire ingestion pipeline and add CLI entry point"
```
