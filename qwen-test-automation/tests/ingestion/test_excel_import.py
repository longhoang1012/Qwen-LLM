import pytest

from qwen_test_automation.models import TestScenario
from qwen_test_automation.ingestion.excel_export import export_scenarios_to_excel
from qwen_test_automation.ingestion.excel_import import (
    read_scenarios_from_excel,
    ExcelImportError,
)


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


def test_read_scenarios_treats_any_non_na_value_as_applicable(tmp_path):
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


def test_read_scenarios_raises_on_blank_id(tmp_path):
    import openpyxl
    out = tmp_path / "testcases.xlsx"
    export_scenarios_to_excel([make_scenario()], str(out))
    wb = openpyxl.load_workbook(str(out))
    ws = wb["Test cases"]
    ws.cell(row=2, column=2).value = None  # column 2 = ID
    wb.save(str(out))
    with pytest.raises(ExcelImportError, match="row 2"):
        read_scenarios_from_excel(str(out))


def test_read_scenarios_raises_on_duplicate_id(tmp_path):
    out = tmp_path / "testcases.xlsx"
    export_scenarios_to_excel(
        [make_scenario(id_="SC-001"), make_scenario(id_="SC-001")], str(out)
    )
    with pytest.raises(ExcelImportError, match="SC-001"):
        read_scenarios_from_excel(str(out))


def test_read_scenarios_coerces_numeric_id_to_string(tmp_path):
    import openpyxl
    out = tmp_path / "testcases.xlsx"
    export_scenarios_to_excel([make_scenario()], str(out))
    wb = openpyxl.load_workbook(str(out))
    ws = wb["Test cases"]
    ws.cell(row=2, column=2).value = 42  # column 2 = ID, numeric
    wb.save(str(out))
    result = read_scenarios_from_excel(str(out))
    assert result[0].id == "42"


def test_read_scenarios_skips_fully_blank_rows(tmp_path):
    out = tmp_path / "testcases.xlsx"
    export_scenarios_to_excel([make_scenario()], str(out))
    import openpyxl
    wb = openpyxl.load_workbook(str(out))
    ws = wb["Test cases"]
    ws.append([None] * 14)  # formatted-but-empty trailing row
    wb.save(str(out))

    result = read_scenarios_from_excel(str(out))
    assert len(result) == 1


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
