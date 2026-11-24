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


def test_write_final_report_cleans_multiline_traceback_note(tmp_path):
    conn = init_db(str(tmp_path / "h.db"))
    scenario = make_scenario()
    testcase = to_testcase(scenario, "WTS")
    insert_testcase(conn, testcase)
    raw = (
        "Traceback (most recent call last):\n"
        "  File \"script.py\", line 10, in <module>\n"
        "AssertionError: expected Dashboard, got Login"
    )
    record_run(conn, testcase.id, "fail", "assertion", raw)
    out = tmp_path / "report.xlsx"
    write_final_report([scenario], conn, str(out))
    wb = openpyxl.load_workbook(str(out))
    main_note = _row_dict(wb["Test cases"], 2)["Ghi chú"]
    assert main_note == "WTS: AssertionError: expected Dashboard, got Login"
    assert "Traceback" not in main_note
    bug_ws = wb["Bug list"]
    bug_note = [row[6].value for row in bug_ws.iter_rows(min_row=2)][0]
    assert bug_note == "AssertionError: expected Dashboard, got Login"
    assert "Traceback" not in bug_note


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
