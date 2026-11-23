import json

import pytest

from qwen_test_automation.ingestion.scenario_generator import (
    generate_scenarios,
    ScenarioParseError,
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


def test_generate_scenarios_raises_when_steps_is_a_string_not_a_list():
    payload = json.dumps([{
        "id": "SC-001", "feature": "Đăng nhập", "group": "Xác thực",
        "screen": "Login", "title": "Đăng nhập với OTP đúng",
        "precondition": "Tài khoản tồn tại",
        "steps": "Mở trang đăng nhập\nNhập OTP",
        "expected_result": "Vào được trang chủ",
        "applicable_platforms": ["WTS"],
    }])
    client = FakeClient(payload)
    with pytest.raises(ScenarioParseError, match="steps"):
        generate_scenarios("doc text", client=client, model="qwen2.5:7b")


def test_generate_scenarios_raises_when_steps_is_empty_list():
    payload = json.dumps([{
        "id": "SC-001", "feature": "Đăng nhập", "group": "Xác thực",
        "screen": "Login", "title": "Đăng nhập với OTP đúng",
        "precondition": "Tài khoản tồn tại", "steps": [],
        "expected_result": "Vào được trang chủ",
        "applicable_platforms": ["WTS"],
    }])
    client = FakeClient(payload)
    with pytest.raises(ScenarioParseError, match="steps"):
        generate_scenarios("doc text", client=client, model="qwen2.5:7b")


def test_generate_scenarios_raises_when_text_field_is_not_a_string():
    payload = json.dumps([{
        "id": "SC-001", "feature": "Đăng nhập", "group": "Xác thực",
        "screen": "Login", "title": "Đăng nhập với OTP đúng",
        "precondition": None, "steps": ["Mở trang"],
        "expected_result": "Vào được trang chủ",
        "applicable_platforms": ["WTS"],
    }])
    client = FakeClient(payload)
    with pytest.raises(ScenarioParseError, match="precondition"):
        generate_scenarios("doc text", client=client, model="qwen2.5:7b")


def test_generate_scenarios_strips_markdown_code_fence():
    fenced = "```json\n" + _valid_scenario_json() + "\n```"
    client = FakeClient(fenced)
    result = generate_scenarios("doc text", client=client, model="qwen2.5:7b")
    assert len(result) == 1
    assert result[0].id == "SC-001"


def test_generate_scenarios_malformed_json_error_includes_raw_response():
    client = FakeClient("not json at all, oops")
    with pytest.raises(ScenarioParseError, match="not json at all"):
        generate_scenarios("doc text", client=client, model="qwen2.5:7b")
