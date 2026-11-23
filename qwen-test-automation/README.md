# Qwen Test Automation

Công cụ tự động hoá test cho WTS/MWTS/MTS (Shinhan Securities), dùng Qwen
chạy local qua Ollama để đỡ tốn token Claude cho các việc lặp lại (đọc
tài liệu, sinh testcase, sinh script, chạy test). Thiết kế đầy đủ xem
[docs/superpowers/specs/2026-11-20-local-qwen-automation-design.md](../docs/superpowers/specs/2026-11-20-local-qwen-automation-design.md).

## Cài đặt (máy mới, kể cả máy khác ngoài máy đang code)

Mã nguồn nằm trên git (repo này), nhưng 3 thứ sau **không** nằm trong git,
phải tự cài/tạo lại trên mỗi máy:

1. **Clone repo** (repo private, cần quyền truy cập GitHub trên máy đó):
   ```bash
   git clone https://github.com/longhoang1012/Qwen-LLM.git
   cd Qwen-LLM/qwen-test-automation
   ```

2. **Python venv + thư viện**:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
   (Project đang chạy tốt trên Python 3.9, nhưng 3.11+ sẽ an toàn hơn về
   lâu dài — một số thư viện tương lai có thể bỏ hỗ trợ 3.9.)

3. **Ollama** (bắt buộc cho mọi bước sinh testcase/script):
   ```bash
   brew install ollama
   ollama pull qwen2.5:7b        # model text/code
   ollama pull qwen2.5vl:7b      # model đọc ảnh/PDF scan
   ```

4. **Playwright** (chỉ cần khi thực sự *chạy* test trên WTS/MWTS, không
   cần để chạy test suite của project):
   ```bash
   .venv/bin/pip install playwright
   .venv/bin/playwright install chromium
   ```

5. **Credentials + host allowlist** (bắt buộc, gitignored — mỗi máy tự tạo
   từ file mẫu, điền giá trị thật, không bao giờ commit):
   ```bash
   mkdir -p config_local
   cp config_examples/credentials.local.json.example config_local/credentials.json
   cp config_examples/host_allowlist.local.json.example config_local/host_allowlist.json
   # rồi mở 2 file trong config_local/ sửa thành giá trị thật
   ```

Mỗi máy chạy độc lập — model Ollama, browser Playwright, credentials và
`history.db` (SQLite lưu lịch sử chạy) đều là trạng thái **riêng của từng
máy**, không đồng bộ qua git.

## Dùng: sinh testcase từ tài liệu (Ingestion)

```bash
cd qwen-test-automation
source .venv/bin/activate
python cli.py generate-scenarios duong_dan_tai_lieu.pdf testcases/ra.xlsx
```

Nhận `.pdf`, `.txt`/`.md` (nội dung Redmine đã export/paste), hoặc
`.png`/`.jpg`/`.jpeg`. Kết quả là file Excel theo đúng cột chuẩn QC
(Tính năng, ID, Nhóm, Màn hình/module, Tiêu đề, Tiền điều kiện, Bước thực
hiện, Kết quả mong đợi, 4 cột nền tảng, Bug ID, Ghi chú) — **review/sửa
tay file Excel này trước khi dùng tiếp**, hệ thống không tự ý chạy test
từ nội dung chưa được duyệt.

## Dùng: sinh và chạy script test (Web Runner)

Phần này hiện là **thư viện Python**, chưa có lệnh CLI riêng — và còn
thiếu bước đọc ngược file Excel đã duyệt thành testcase (xem "Còn thiếu"
bên dưới). Ví dụ gọi trực tiếp:

```python
from qwen_test_automation.models import TestCase
from qwen_test_automation.history.db import init_db
from qwen_test_automation.config.credentials import load_credentials
from qwen_test_automation.config.host_allowlist import load_allowed_hosts
from qwen_test_automation.llm.ollama_client import OllamaClient
from qwen_test_automation.runner.web_runner import ensure_script_generated, run_web_testcase

client = OllamaClient()
allowed_hosts = load_allowed_hosts("config_local/host_allowlist.json")
credentials = load_credentials("config_local/credentials.json")
conn = init_db("history.db")

testcase = TestCase(
    id="TC-001", feature="Đăng nhập", precondition="Tài khoản tồn tại",
    steps=["Mở trang đăng nhập", "Nhập tài khoản/mật khẩu", "Nhập OTP"],
    expected_result="Vào được trang chủ", platform="WTS",
)

# Bước 1 — sinh script, lưu vào scripts/ để bạn tự xem/sửa trước khi chạy.
ensure_script_generated(testcase, client, "qwen2.5-coder:7b", "scripts", allowed_hosts)

# Bước 2 — chạy (tách biệt, chủ động, sau khi đã xem qua script ở bước 1).
status = run_web_testcase(
    testcase, "https://<host-thật-trong-allowlist>",
    allowed_hosts, "scripts", conn,
    credentials=credentials, account="<số-tài-khoản-test>",
)
print(status)  # "pass" | "fail" | "pending_claude_review" | "blocked"
```

## Trạng thái hiện tại / còn thiếu

- ✅ Foundation (model, config, SQLite history, Ollama client)
- ✅ Ingestion (docs → testcase Excel theo chuẩn QC)
- ✅ Web Runner (chạy test WTS/MWTS an toàn — có safety gate, retry,
  phân loại lỗi) — nhưng mới có API Python, **chưa có lệnh CLI**, và
  **chưa đọc được file Excel đã duyệt** để lấy testcase chạy (phải tự
  gõ `TestCase(...)` như ví dụ trên).
- ⬜ Mobile Runner (MTS, Android/iOS)
- ⬜ Reporting (gộp kết quả thành Excel report cuối)
- ⬜ Redmine API thật (hiện chỉ đọc file `.txt`/`.md` đã export tay)

## An toàn

- Không bao giờ commit `config_local/` (credentials thật) — đã gitignore.
- `runner` từ chối chạy script (của chính nó hoặc script bạn tự sửa) nếu
  phát hiện host không nằm trong `host_allowlist.json`.
- Giao dịch thật (đặt/sửa/huỷ lệnh, chuyển/rút tiền) được dặn trong prompt
  sinh script là không được tự bấm xác nhận — nhưng đây vẫn chỉ là chỉ dẫn
  cho Qwen, **hãy luôn tự đọc lại script trước khi chạy lần đầu**, nhất là
  với testcase liên quan giao dịch thật.
