from __future__ import annotations

import json

from qwen_test_automation.models import TestCase, VALID_PLATFORMS

_PROMPT_TEMPLATE = """\
You are a QA test-case writer. Read the document below and produce test \
cases for it as a JSON array only — no prose, no markdown fences.

Each element must have exactly these fields:
- id: string
- feature: string
- precondition: string
- steps: array of strings
- expected_result: string
- platform: one of {platforms}

Document:
{doc_text}
"""


class TestcaseParseError(Exception):
    pass


def generate_testcases(
    doc_text: str,
    client,
    model: str,
    images: list[str] | None = None,
) -> list[TestCase]:
    prompt = _PROMPT_TEMPLATE.format(
        platforms=", ".join(sorted(VALID_PLATFORMS)),
        doc_text=doc_text,
    )
    response_text = client.generate(model=model, prompt=prompt, images=images)

    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise TestcaseParseError(f"Qwen did not return a valid testcase JSON array: {e}") from e

    if not isinstance(parsed, list):
        raise TestcaseParseError("Qwen did not return a valid testcase JSON array: not a list")

    if len(parsed) == 0:
        raise TestcaseParseError("Qwen returned an empty testcase list")

    testcases = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise TestcaseParseError(f"testcase #{i} is not a JSON object: {item!r}")

        missing = [
            f for f in ("id", "feature", "precondition", "steps", "expected_result", "platform")
            if f not in item
        ]
        if missing:
            raise TestcaseParseError(f"testcase #{i} missing field(s): {', '.join(missing)}")

        if not isinstance(item["steps"], list) or not all(
            isinstance(step, str) for step in item["steps"]
        ):
            raise TestcaseParseError(f"testcase #{i} field 'steps' must be a list of strings")

        testcase = TestCase.from_dict(item)
        if testcase.platform not in VALID_PLATFORMS:
            raise TestcaseParseError(
                f"testcase {item.get('id')} has invalid platform: {item.get('platform')}"
            )
        testcases.append(testcase)

    return testcases
