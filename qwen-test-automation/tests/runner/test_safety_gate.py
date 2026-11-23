import pytest

from qwen_test_automation.runner.safety_gate import assert_host_allowed, HostNotAllowedError


def test_assert_host_allowed_passes_for_allowed_host():
    assert_host_allowed("https://uat-wts.shinhan.internal/login", {"uat-wts.shinhan.internal"})


def test_assert_host_allowed_raises_for_disallowed_host():
    with pytest.raises(HostNotAllowedError, match="prod-wts.shinhan.com"):
        assert_host_allowed("https://prod-wts.shinhan.com/login", {"uat-wts.shinhan.internal"})


def test_assert_host_allowed_raises_when_allowlist_empty():
    with pytest.raises(HostNotAllowedError):
        assert_host_allowed("https://uat-wts.shinhan.internal/login", set())
