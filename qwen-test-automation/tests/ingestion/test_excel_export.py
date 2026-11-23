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


def test_export_does_not_treat_leading_equals_as_formula(tmp_path):
    out = tmp_path / "testcases.xlsx"
    sc = make_scenario()
    sc.expected_result = "=> Hiển thị thông báo lỗi"
    export_scenarios_to_excel([sc], str(out))
    wb = openpyxl.load_workbook(str(out))
    ws = wb["Test cases"]
    cell = ws.cell(row=2, column=8)  # Kết quả mong đợi
    assert cell.value == "=> Hiển thị thông báo lỗi"
    assert cell.data_type == "s"
