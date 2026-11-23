import json

import pytest

from qwen_test_automation.llm.testcase_generator import (
    generate_testcases,
    TestcaseParseError,
)


class FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text

    def generate(self, model, prompt, images=None):
        return self.response_text


def test_generate_testcases_parses_valid_json_array():
    payload = json.dumps([{
        "id": "TC-001", "feature": "Login", "precondition": "Account exists",
        "steps": ["Open app", "Login"], "expected_result": "Dashboard shown",
        "platform": "MTS-Android",
    }])
    client = FakeClient(payload)
    result = generate_testcases("some doc text", client=client, model="qwen2.5:7b")
    assert len(result) == 1
    assert result[0].id == "TC-001"
    assert result[0].platform == "MTS-Android"


def test_generate_testcases_raises_on_malformed_json():
    client = FakeClient("not json at all")
    with pytest.raises(TestcaseParseError):
        generate_testcases("some doc text", client=client, model="qwen2.5:7b")


def test_generate_testcases_raises_on_invalid_platform():
    payload = json.dumps([{
        "id": "TC-001", "feature": "Login", "precondition": "",
        "steps": ["Open app"], "expected_result": "ok",
        "platform": "NotAPlatform",
    }])
    client = FakeClient(payload)
    with pytest.raises(TestcaseParseError):
        generate_testcases("some doc text", client=client, model="qwen2.5:7b")


def test_generate_testcases_raises_on_missing_field():
    payload = json.dumps([{
        "id": "TC-001", "feature": "Login", "precondition": "Account exists",
        "expected_result": "ok", "platform": "WTS",
        # "steps" missing
    }])
    client = FakeClient(payload)
    with pytest.raises(TestcaseParseError, match="steps"):
        generate_testcases("some doc text", client=client, model="qwen2.5:7b")


def test_generate_testcases_raises_on_non_dict_item():
    payload = json.dumps(["not a testcase object"])
    client = FakeClient(payload)
    with pytest.raises(TestcaseParseError):
        generate_testcases("some doc text", client=client, model="qwen2.5:7b")


def test_generate_testcases_raises_on_steps_not_list_of_strings():
    payload = json.dumps([{
        "id": "TC-001", "feature": "Login", "precondition": "Account exists",
        "steps": "Open app", "expected_result": "ok", "platform": "WTS",
    }])
    client = FakeClient(payload)
    with pytest.raises(TestcaseParseError, match="steps"):
        generate_testcases("some doc text", client=client, model="qwen2.5:7b")


def test_generate_testcases_raises_on_empty_list():
    client = FakeClient(json.dumps([]))
    with pytest.raises(TestcaseParseError):
        generate_testcases("some doc text", client=client, model="qwen2.5:7b")
