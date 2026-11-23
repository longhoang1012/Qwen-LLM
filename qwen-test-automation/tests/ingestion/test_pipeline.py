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
