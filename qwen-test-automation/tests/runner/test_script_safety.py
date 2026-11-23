import pytest

from qwen_test_automation.runner.script_safety import (
    strip_code_fence,
    assert_script_compiles,
    assert_script_hosts_allowed,
    ScriptCompileError,
)
from qwen_test_automation.runner.safety_gate import HostNotAllowedError


def test_strip_code_fence_removes_python_fence():
    fenced = "```python\nprint('hi')\n```"
    assert strip_code_fence(fenced) == "print('hi')"


def test_strip_code_fence_leaves_unfenced_text_untouched():
    assert strip_code_fence("print('hi')") == "print('hi')"


def test_assert_script_compiles_passes_for_valid_python():
    assert_script_compiles("import sys\nsys.exit(0)\n")


def test_assert_script_compiles_raises_for_invalid_syntax():
    with pytest.raises(ScriptCompileError):
        assert_script_compiles("def f(:\n")


def test_assert_script_hosts_allowed_passes_when_no_disallowed_host():
    assert_script_hosts_allowed(
        "page.goto('https://uat.example.internal/login')",
        {"uat.example.internal"},
    )


def test_assert_script_hosts_allowed_passes_when_no_url_literal():
    assert_script_hosts_allowed(
        "page.goto(os.environ['QWEN_TEST_BASE_URL'])",
        {"uat.example.internal"},
    )


def test_assert_script_hosts_allowed_raises_for_disallowed_host():
    with pytest.raises(HostNotAllowedError, match="prod.evil.com"):
        assert_script_hosts_allowed(
            "page.goto('https://prod.evil.com/login')",
            {"uat.example.internal"},
        )
