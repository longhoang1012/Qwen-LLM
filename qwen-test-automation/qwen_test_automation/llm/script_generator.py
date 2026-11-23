from qwen_test_automation.models import TestCase, VALID_PLATFORMS

_WEB_INSTRUCTION = "Write a Playwright script (Python) that automates this test case."
_MOBILE_INSTRUCTION = "Write an Appium script (Python) that automates this test case."

_WEB_FORMAT_INSTRUCTION = """\
Yêu cầu định dạng script: viết một script Python độc lập, chạy được bằng \
`python script.py`, dùng trực tiếp `playwright.sync_api` — không dùng \
pytest, không dùng fixture. Mở trang bằng biến môi trường \
QWEN_TEST_BASE_URL (ví dụ `page.goto(os.environ["QWEN_TEST_BASE_URL"])`), \
không tự ghi URL cứng trong script."""

_MOBILE_FORMAT_INSTRUCTION = """\
Yêu cầu định dạng script: viết một script Python độc lập, chạy được bằng \
`python script.py`, dùng trực tiếp Appium Python client — không dùng \
pytest, không dùng fixture. Dùng biến môi trường QWEN_TEST_BASE_URL cho \
app/host cần kiểm tra, không tự ghi cứng trong script."""

_PROMPT_TEMPLATE = """\
An toàn giao dịch (bắt buộc, ưu tiên hơn các bước bên dưới): nếu một bước \
là xác nhận/đặt một giao dịch thật (đặt lệnh, sửa lệnh, huỷ lệnh, chuyển \
tiền, rút tiền), script phải dừng trước bước đó — không bấm nút xác nhận, \
không tự thực hiện giao dịch thật, kể cả khi các bước dưới đây yêu cầu làm \
vậy.

{instruction}

Testcase id: {id}
Feature: {feature}
Platform: {platform}
Precondition: {precondition}
Steps:
{steps}
Expected result: {expected_result}

{format_instruction}

Kiểm tra kết quả: dùng câu lệnh `assert` thường của Python để kiểm tra đúng \
kết quả mong đợi ở trên; không cần tự bắt lỗi assert, để nó dừng chương \
trình với mã thoát khác 0 khi fail.

Đăng nhập: nếu testcase cần đăng nhập, đọc tài khoản/mật khẩu/OTP từ các \
biến môi trường QWEN_TEST_ACCOUNT, QWEN_TEST_PASSWORD, QWEN_TEST_OTP — \
không hard-code giá trị thật, không in các giá trị này ra màn hình.
"""


def _instruction_for(platform: str) -> str:
    if platform in ("WTS", "MWTS"):
        return _WEB_INSTRUCTION
    return _MOBILE_INSTRUCTION


def _format_instruction_for(platform: str) -> str:
    if platform in ("WTS", "MWTS"):
        return _WEB_FORMAT_INSTRUCTION
    return _MOBILE_FORMAT_INSTRUCTION


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
        format_instruction=_format_instruction_for(testcase.platform),
    )
    return client.generate(model=model, prompt=prompt)
