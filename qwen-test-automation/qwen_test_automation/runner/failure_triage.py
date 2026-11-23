_LOCATOR_SIGNATURES = ("Timeout", "waiting for", "Locator expected")


def classify_failure(stderr: str) -> str:
    if "AssertionError" in stderr:
        # Playwright's expect() raises AssertionError when a locator
        # condition times out — that is a structural/UI failure, not a
        # business-logic assertion, even though the exception type says
        # "AssertionError".
        if any(sig in stderr for sig in _LOCATOR_SIGNATURES):
            return "locator"
        return "assertion"
    return "locator"
