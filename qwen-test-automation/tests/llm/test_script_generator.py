import pytest

from qwen_test_automation.models import TestCase
from qwen_test_automation.llm.script_generator import generate_script


class FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text
        self.last_prompt = None

    def generate(self, model, prompt, images=None):
        self.last_prompt = prompt
        return self.response_text


def make_testcase(platform="WTS"):
    return TestCase(
        id="TC-001", feature="Login", precondition="Account exists",
        steps=["Open login page", "Enter account", "Submit"],
        expected_result="Dashboard shown", platform=platform,
    )


def test_generate_script_returns_client_response():
    client = FakeClient("<generated playwright script>")
    script = generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    assert script == "<generated playwright script>"
    assert "TC-001" in client.last_prompt


def test_generate_script_raises_on_invalid_platform():
    tc = make_testcase("WTS")
    tc.platform = "NotAPlatform"
    client = FakeClient("irrelevant")
    with pytest.raises(ValueError):
        generate_script(tc, client=client, model="qwen2.5-coder:7b")


def test_generate_script_prompt_includes_platform_and_precondition():
    client = FakeClient("script")
    generate_script(make_testcase("MTS-Android"), client=client, model="qwen2.5-coder:7b")
    assert "MTS-Android" in client.last_prompt
    assert "Account exists" in client.last_prompt


def test_generate_script_prompt_differs_between_web_platforms():
    client_wts = FakeClient("script")
    generate_script(make_testcase("WTS"), client=client_wts, model="qwen2.5-coder:7b")
    client_mwts = FakeClient("script")
    generate_script(make_testcase("MWTS"), client=client_mwts, model="qwen2.5-coder:7b")
    assert client_wts.last_prompt != client_mwts.last_prompt


def test_generate_script_prompt_differs_between_mobile_platforms():
    client_android = FakeClient("script")
    generate_script(make_testcase("MTS-Android"), client=client_android, model="qwen2.5-coder:7b")
    client_ios = FakeClient("script")
    generate_script(make_testcase("MTS-iOS"), client=client_ios, model="qwen2.5-coder:7b")
    assert client_android.last_prompt != client_ios.last_prompt
