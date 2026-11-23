from __future__ import annotations

import json

from qwen_test_automation.models import TestScenario, VALID_PLATFORMS

_REQUIRED_FIELDS = (
    "id", "feature", "group", "screen", "title",
    "precondition", "steps", "expected_result", "applicable_platforms",
)
_REQUIRED_STRING_FIELDS = (
    "id", "feature", "group", "screen", "title", "precondition", "expected_result",
)

_PROMPT_TEMPLATE = """\
Bạn là một QC viết test case cho hệ thống giao dịch chứng khoán. Đọc tài \
liệu dưới đây và sinh ra các kịch bản test dưới dạng JSON array duy nhất \
(không kèm markdown, không kèm lời giải thích).

Mỗi phần tử có đúng các field sau:
- id: string
- feature: string (tính năng)
- group: string (nhóm)
- screen: string (màn hình/module)
- title: string (tiêu đề)
- precondition: string (tiền điều kiện)
- steps: mảng string (bước thực hiện)
- expected_result: string (kết quả mong đợi)
- applicable_platforms: mảng, chỉ chứa các giá trị trong {platforms}

Viết bằng giọng văn trung tính của một QC: nêu điều kiện - thao tác - kết \
quả, không tự xưng "tôi"/"mình", không dùng nhãn quy trình hay nhắc tới \
công cụ ("QC xác nhận", "Claude", "đã test", "chạy tay"...).

Tài liệu:
{doc_text}
"""


class ScenarioParseError(Exception):
    pass


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def generate_scenarios(
    doc_text: str,
    client,
    model: str,
    images: list[str] | None = None,
) -> list[TestScenario]:
    prompt = _PROMPT_TEMPLATE.format(
        platforms=", ".join(sorted(VALID_PLATFORMS)),
        doc_text=doc_text,
    )
    response_text = client.generate(model=model, prompt=prompt, images=images)
    cleaned = _strip_code_fence(response_text)
    snippet = response_text[:500]

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ScenarioParseError(
            f"Qwen did not return a valid scenario JSON array: {e}. Raw response: {snippet!r}"
        ) from e

    if not isinstance(parsed, list):
        raise ScenarioParseError(
            f"Qwen did not return a valid scenario JSON array: not a list. Raw response: {snippet!r}"
        )

    scenarios = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ScenarioParseError(f"scenario #{i} is not a JSON object: {item!r}")

        missing = [f for f in _REQUIRED_FIELDS if f not in item]
        if missing:
            raise ScenarioParseError(f"scenario #{i} missing field(s): {', '.join(missing)}")

        for field in _REQUIRED_STRING_FIELDS:
            if not isinstance(item[field], str):
                raise ScenarioParseError(
                    f"scenario #{i} field '{field}' must be a string, got {item[field]!r}"
                )

        steps = item["steps"]
        if (
            not isinstance(steps, list)
            or len(steps) == 0
            or not all(isinstance(s, str) for s in steps)
        ):
            raise ScenarioParseError(
                f"scenario #{i} field 'steps' must be a non-empty list of strings: {steps!r}"
            )

        platforms = item["applicable_platforms"]
        if (
            not isinstance(platforms, list)
            or len(platforms) == 0
            or not all(p in VALID_PLATFORMS for p in platforms)
        ):
            raise ScenarioParseError(
                f"scenario #{i} field 'applicable_platforms' must be a non-empty "
                f"list drawn from {sorted(VALID_PLATFORMS)}: {platforms!r}"
            )

        scenarios.append(TestScenario.from_dict(item))

    return scenarios
