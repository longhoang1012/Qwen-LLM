from qwen_test_automation.runner.failure_triage import classify_failure


def test_classify_assertion_error_as_assertion():
    stderr = "Traceback (most recent call last):\n  ...\nAssertionError: expected Dashboard, got Login"
    assert classify_failure(stderr) == "assertion"


def test_classify_timeout_error_as_locator():
    stderr = "playwright._impl._api_types.TimeoutError: Timeout 30000ms exceeded."
    assert classify_failure(stderr) == "locator"


def test_classify_unknown_or_empty_defaults_to_locator():
    assert classify_failure("") == "locator"
    assert classify_failure("SomeWeirdCrash: boom") == "locator"


def test_classify_playwright_expect_timeout_as_locator_not_assertion():
    stderr = (
        "AssertionError: Locator expected to be visible\n"
        "Call log:\n"
        "  - waiting for locator(\"#dashboard\") to be visible\n"
        "  - Timeout 5000ms exceeded.\n"
    )
    assert classify_failure(stderr) == "locator"
