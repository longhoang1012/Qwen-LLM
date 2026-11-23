from qwen_test_automation.models import TestCase, VALID_PLATFORMS


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
