import pytest

from qwen_test_automation.models import TestCase, VALID_PLATFORMS, TestScenario, to_testcase


def test_valid_platforms_contains_expected_four():
    assert VALID_PLATFORMS == {"WTS", "MWTS", "MTS-Android", "MTS-iOS"}


def test_testcase_round_trips_through_dict():
    tc = TestCase(
        id="TC-001",
        feature="Login",
        precondition="Account exists",
        steps=["Open app", "Enter account", "Enter password", "Tap login"],
        expected_result="User lands on dashboard",
        platform="MTS-Android",
    )
    data = tc.to_dict()
    restored = TestCase.from_dict(data)
    assert restored == tc


def make_scenario(applicable_platforms=("WTS", "MWTS")):
    return TestScenario(
        id="SC-001", feature="Đăng nhập", group="Xác thực", screen="Login",
        title="Đăng nhập với OTP đúng",
        precondition="Tài khoản tồn tại, đã đăng ký OTP",
        steps=["Mở trang đăng nhập", "Nhập tài khoản/mật khẩu", "Nhập OTP"],
        expected_result="Vào được trang chủ sau khi xác thực",
        applicable_platforms=list(applicable_platforms),
    )


def test_scenario_round_trips_through_dict():
    sc = make_scenario()
    assert TestScenario.from_dict(sc.to_dict()) == sc


def test_to_testcase_derives_platform_specific_testcase():
    sc = make_scenario(("WTS", "MWTS"))
    tc = to_testcase(sc, "WTS")
    assert tc.id == "SC-001-WTS"
    assert tc.feature == "Đăng nhập với OTP đúng"
    assert tc.platform == "WTS"
    assert tc.steps == sc.steps
    assert tc.precondition == sc.precondition
    assert tc.expected_result == sc.expected_result


def test_to_testcase_raises_when_platform_not_applicable():
    sc = make_scenario(("WTS",))
    with pytest.raises(ValueError):
        to_testcase(sc, "MTS-Android")
