# Qwen Test Automation

Công cụ tự động hoá test cho WTS/MWTS/MTS (Shinhan Securities), dùng Qwen
chạy local qua Ollama để đỡ tốn token Claude cho các việc lặp lại (đọc
tài liệu, sinh testcase, sinh script, chạy test). Thiết kế đầy đủ xem
[docs/superpowers/specs/2026-11-20-local-qwen-automation-design.md](../docs/superpowers/specs/2026-11-20-local-qwen-automation-design.md).

## Cài đặt nhanh (1 lệnh)

```bash
cd qwen-test-automation
./setup.sh                # venv + Ollama + 2 model + config_local/
./setup.sh --with-browser # thêm cả Playwright + Chromium (~300MB, cần khi chạy test thật)
```

Script tự bỏ qua phần đã cài nếu chạy lại — an toàn khi chạy nhiều lần.
Chi tiết từng bước script làm, xem phần dưới.

## Cài đặt (máy mới, kể cả máy khác ngoài máy đang code)

Mã nguồn nằm trên git (repo này), nhưng 3 thứ sau **không** nằm trong git,
phải tự cài/tạo lại trên mỗi máy (`setup.sh` ở trên làm tự động cả 3 bước này):

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

## Dùng: docs → testcase + script (1 lệnh, chỉ sinh, không chạy)

```bash
cd qwen-test-automation
source .venv/bin/activate
python cli.py prepare-tests duong_dan_tai_lieu.pdf testcases/ra.xlsx
```

Nhận `.pdf`, `.txt`/`.md` (nội dung Redmine đã export/paste), hoặc
`.png`/`.jpg`/`.jpeg`. Lệnh này gộp 2 bước (sinh testcase Excel + sinh
script cho từng testcase WTS/MWTS vào `scripts/`) — **nhưng cố tình
không chạy gì cả**. Review/sửa `testcases/ra.xlsx` và các file trong
`scripts/` trước khi qua bước chạy, nhất là với testcase liên quan giao
dịch thật — đây là ranh giới an toàn duy nhất hệ thống giữ lại, không bỏ
qua được bằng cờ nào.

Nếu muốn làm từng bước riêng (ví dụ chỉ sinh testcase trước, để dành sinh
script sau): `python cli.py generate-scenarios ...` rồi
`python cli.py generate-script ...` — xem `--help` từng lệnh.

## Dùng: chạy test + xuất report cuối

```bash
python cli.py run-tests testcases/ra.xlsx \
    --url https://<host-thật-nằm-trong-host_allowlist.json> \
    --account <số-tài-khoản-test>
```

Chạy mọi script đã có trong `scripts/` (không tự sinh thêm), in
`pass`/`fail`/`pending_claude_review`/`blocked` cho từng testcase, rồi tự
xuất **report cuối** `testcases/ra_report.xlsx` (đổi bằng `--report`) —
sheet "Test cases" với trạng thái thật Pass/Fail/Blocked/Not run cho
từng testcase×nền tảng, và sheet "Bug list" liệt kê các ca Fail. Testcase
thuộc nền tảng mobile (MTS-Android/MTS-iOS) bị bỏ qua rõ ràng (chưa có
Mobile Runner).

Lưu ý: ID testcase do Qwen tự đặt (vd "TC-001"), nên nếu chạy
`prepare-tests` cho một tài liệu khác mà trùng ID với lần trước,
`scripts/` sẽ **dùng lại** script cũ thay vì sinh mới — CLI sẽ cảnh báo
rõ dòng nào bị "dùng lại", nhưng nếu nghi ngờ hãy dùng `--scripts-dir`
riêng cho mỗi tài liệu để tránh nhầm lẫn.

Muốn gọi trực tiếp bằng Python (ví dụ để tích hợp vào chỗ khác) thay vì
qua CLI, xem `cli.py`'s `_generate_scripts`/`_run_tests` — chúng gọi
thẳng `ensure_script_generated`/`run_web_testcase` trong
`qwen_test_automation.runner.web_runner`.

## Trạng thái hiện tại / còn thiếu

- ✅ Foundation (model, config, SQLite history, Ollama client)
- ✅ Ingestion (docs → testcase Excel theo chuẩn QC)
- ✅ Web Runner (chạy test WTS/MWTS an toàn — safety gate, retry, phân
  loại lỗi)
- ✅ Report cuối (Pass/Fail/Blocked/Not run + sheet Bug list)
- ✅ CLI đầy đủ: `prepare-tests` (docs → testcase + script, chỉ sinh) →
  `run-tests` (chạy + xuất report) — đúng 2 lệnh cho toàn bộ luồng
  WTS/MWTS, với 1 điểm dừng cố ý để review script trước khi chạy.
- ⬜ Mobile Runner (MTS, Android/iOS)
- ⬜ Redmine API thật (hiện chỉ đọc file `.txt`/`.md` đã export tay)

## An toàn

- Không bao giờ commit `config_local/` (credentials thật) — đã gitignore.
- `runner` từ chối chạy script (của chính nó hoặc script bạn tự sửa) nếu
  phát hiện host không nằm trong `host_allowlist.json`.
- Giao dịch thật (đặt/sửa/huỷ lệnh, chuyển/rút tiền) được dặn trong prompt
  sinh script là không được tự bấm xác nhận — nhưng đây vẫn chỉ là chỉ dẫn
  cho Qwen, **hãy luôn tự đọc lại script trước khi chạy lần đầu**, nhất là
  với testcase liên quan giao dịch thật.
