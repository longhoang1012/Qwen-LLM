import re

import openpyxl

from qwen_test_automation.models import TestScenario
from qwen_test_automation.ingestion.excel_export import PLATFORM_COLUMNS

_STEP_PREFIX = re.compile(r"^\d+\.\s*")


class ExcelImportError(Exception):
    pass


def read_scenarios_from_excel(path: str) -> list:
    wb = openpyxl.load_workbook(path)
    ws = wb["Test cases"]
    header = [cell.value for cell in ws[1]]

    scenarios = []
    seen_ids = set()
    for row in ws.iter_rows(min_row=2):
        values = {header[i]: cell.value for i, cell in enumerate(row)}

        # A row left over from Excel formatting (e.g. a QC's trailing
        # styled-but-empty rows) has every cell None — skip it rather
        # than treating it as a malformed scenario.
        if all(v is None for v in values.values()):
            continue

        row_number = row[0].row
        raw_id = values.get("ID")
        if raw_id is None or str(raw_id).strip() == "":
            raise ExcelImportError(f"row {row_number}: missing ID")
        scenario_id = str(raw_id)
        if scenario_id in seen_ids:
            raise ExcelImportError(f"row {row_number}: duplicate ID {scenario_id!r}")
        seen_ids.add(scenario_id)

        steps_raw = values.get("Bước thực hiện") or ""
        steps = [
            _STEP_PREFIX.sub("", line)
            for line in steps_raw.split("\n")
            if line.strip()
        ]

        applicable_platforms = [
            p for p in PLATFORM_COLUMNS if values.get(p) not in (None, "N/A")
        ]

        scenarios.append(TestScenario(
            id=scenario_id,
            feature=values.get("Tính năng"),
            group=values.get("Nhóm"),
            screen=values.get("Màn hình/module"),
            title=values.get("Tiêu đề"),
            precondition=values.get("Tiền điều kiện"),
            steps=steps,
            expected_result=values.get("Kết quả mong đợi"),
            applicable_platforms=applicable_platforms,
        ))

    return scenarios
