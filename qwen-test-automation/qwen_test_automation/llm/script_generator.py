from qwen_test_automation.models import TestCase, VALID_PLATFORMS

_WEB_INSTRUCTION = "Write a Playwright script (Python) that automates this test case."
_MOBILE_INSTRUCTION = "Write an Appium script (Python) that automates this test case."

_PROMPT_TEMPLATE = """\
{instruction}

Testcase id: {id}
Feature: {feature}
Platform: {platform}
Precondition: {precondition}
Steps:
{steps}
Expected result: {expected_result}
"""


def _instruction_for(platform: str) -> str:
    if platform in ("WTS", "MWTS"):
        return _WEB_INSTRUCTION
    return _MOBILE_INSTRUCTION


def generate_script(testcase: TestCase, client, model: str) -> str:
    if testcase.platform not in VALID_PLATFORMS:
        raise ValueError(f"unknown platform: {testcase.platform}")

    prompt = _PROMPT_TEMPLATE.format(
        instruction=_instruction_for(testcase.platform),
        id=testcase.id,
        feature=testcase.feature,
        platform=testcase.platform,
        precondition=testcase.precondition,
        steps="\n".join(f"- {step}" for step in testcase.steps),
        expected_result=testcase.expected_result,
    )
    return client.generate(model=model, prompt=prompt)
