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


def test_generate_script_prompt_forbids_real_transaction_submit():
    client = FakeClient("script")
    generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    assert "không bấm" in client.last_prompt or "dừng trước" in client.last_prompt


def test_generate_script_prompt_requires_standalone_sync_api_script():
    client = FakeClient("script")
    generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    assert "playwright.sync_api" in client.last_prompt
    assert "pytest" in client.last_prompt  # instructed not to use it


def test_generate_script_prompt_tells_qwen_to_read_credentials_from_env():
    client = FakeClient("script")
    generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    assert "QWEN_TEST_ACCOUNT" in client.last_prompt
    assert "QWEN_TEST_PASSWORD" in client.last_prompt
    assert "QWEN_TEST_OTP" in client.last_prompt


def test_generate_script_prompt_tells_qwen_to_use_base_url_env_var():
    client = FakeClient("script")
    generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    assert "QWEN_TEST_BASE_URL" in client.last_prompt


def test_generate_script_prompt_puts_safety_rule_before_testcase_steps():
    client = FakeClient("script")
    generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    safety_idx = client.last_prompt.find("dừng trước")
    steps_idx = client.last_prompt.find("Steps:")
    assert safety_idx != -1 and steps_idx != -1
    assert safety_idx < steps_idx


def test_generate_script_prompt_tells_qwen_to_assert_expected_result():
    client = FakeClient("script")
    generate_script(make_testcase("WTS"), client=client, model="qwen2.5-coder:7b")
    assert "assert" in client.last_prompt.lower()


def test_generate_script_prompt_mobile_does_not_mention_playwright():
    client = FakeClient("script")
    generate_script(make_testcase("MTS-Android"), client=client, model="qwen2.5-coder:7b")
    assert "playwright" not in client.last_prompt.lower()
