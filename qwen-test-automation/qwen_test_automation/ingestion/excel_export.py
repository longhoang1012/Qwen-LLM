import openpyxl

_PLATFORM_COLUMNS = ["WTS", "MWTS", "MTS-Android", "MTS-iOS"]

_HEADER = (
    ["Tính năng", "ID", "Nhóm", "Màn hình/module", "Tiêu đề",
     "Tiền điều kiện", "Bước thực hiện", "Kết quả mong đợi"]
    + _PLATFORM_COLUMNS
    + ["Bug ID", "Ghi chú"]
)


def export_scenarios_to_excel(scenarios: list, path: str) -> None:
    if len(scenarios) == 0:
        raise ValueError("no scenarios to export")

    kept = [s for s in scenarios if s.applicable_platforms]
    if len(kept) == 0:
        raise ValueError("all scenarios were dropped: none apply to any platform")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Test cases"
    ws.append(_HEADER)

    for scenario in kept:
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
        for platform in _PLATFORM_COLUMNS:
            row.append("Not run" if platform in scenario.applicable_platforms else "N/A")
        row.append("")  # Bug ID
        row.append("")  # Ghi chú
        ws.append(row)
        # openpyxl infers a "formula" type for any string starting with
        # "=" (common in Vietnamese QC text, e.g. "=> Hiển thị..."), which
        # Excel then tries to evaluate. Force every cell in the row we
        # just wrote back to plain string type.
        for cell in ws[ws.max_row]:
            cell.data_type = "s"

    wb.save(path)
