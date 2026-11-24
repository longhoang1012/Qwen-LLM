import openpyxl

from qwen_test_automation.models import to_testcase
from qwen_test_automation.ingestion.excel_export import PLATFORM_COLUMNS
from qwen_test_automation.history.db import get_latest_run

_STATUS_MAP = {
    "pass": "Pass",
    "fail": "Fail",
    "blocked": "Blocked",
    "pending_claude_review": "Not run",
}

_MAIN_HEADER = (
    ["Tính năng", "ID", "Nhóm", "Màn hình/module", "Tiêu đề",
     "Tiền điều kiện", "Bước thực hiện", "Kết quả mong đợi"]
    + PLATFORM_COLUMNS
    + ["Bug ID", "Ghi chú"]
)

_BUG_HEADER = ["Testcase ID", "Nền tảng", "Tính năng", "Tiêu đề", "Mức độ", "Bug ID", "Ghi chú"]


def _clean_note(message: str) -> str:
    """Scripts fail with a Python/Playwright traceback — several lines of
    file paths and call-stack frames that don't belong in a QC-facing
    note. The actual exception or assertion is reliably the last
    non-empty line, so keep only that."""
    if not message:
        return ""
    lines = [line.strip() for line in message.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def write_final_report(scenarios: list, conn, out_path: str) -> None:
    if len(scenarios) == 0:
        raise ValueError("no scenarios to report")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Test cases"
    ws.append(_MAIN_HEADER)

    bug_rows = []

    for scenario in scenarios:
        steps_text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(scenario.steps))
        row = [
            scenario.feature,
            scenario.id,
            scenario.group,
            scenario.screen,
            scenario.title,
            scenario.precondition,
            steps_text,
            scenario.expected_result,
        ]

        notes = []
        for platform in PLATFORM_COLUMNS:
            if platform not in scenario.applicable_platforms:
                row.append("N/A")
                continue

            testcase_id = to_testcase(scenario, platform).id
            run = get_latest_run(conn, testcase_id)
            status = _STATUS_MAP.get(run["status"], "Not run") if run else "Not run"
            row.append(status)

            if run and status in ("Fail", "Blocked"):
                notes.append(f"{platform}: {_clean_note(run['message'])}")
            if status == "Fail":
                bug_rows.append([
                    testcase_id, platform, scenario.feature, scenario.title,
                    "", "", _clean_note(run["message"]),
                ])

        row.append("")  # Bug ID
        row.append("; ".join(notes))  # Ghi chú
        ws.append(row)
        for cell in ws[ws.max_row]:
            cell.data_type = "s"

    bugs = wb.create_sheet("Bug list")
    bugs.append(_BUG_HEADER)
    for bug_row in bug_rows:
        bugs.append(bug_row)
        for cell in bugs[bugs.max_row]:
            cell.data_type = "s"

    wb.save(out_path)
