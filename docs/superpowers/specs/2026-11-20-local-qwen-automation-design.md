# Local Qwen LLM Automation cho test WTS/MWTS/MTS

Ngày: 2026-11-20
Người quyết định: Long (long.lh@shinhan.com)

## 1. Bối cảnh & lý do (Intent)

Hiện tại việc sinh testcase, viết script automation và chạy test cho các hệ thống
giao dịch của Shinhan Securities (WTS, MWTS, MTS) đang dựa vào Claude qua API/chat,
tốn token cho những việc lặp đi lặp lại (đọc tài liệu, sinh testcase, sinh script,
chạy test theo kịch bản đã biết). Mục tiêu là chuyển phần việc "máy làm được, lặp
lại nhiều lần" sang một LLM chạy local (Qwen, qua Ollama) và một bộ automation
script chạy không cần AI, chỉ giữ Claude (Claude in Chrome / Claude mobile tool)
cho những việc thật sự cần khả năng "hiểu" linh hoạt.

Đây là người dùng cá nhân (QA/automation cho riêng Long), chạy trên máy cá nhân
(MacBook, Apple M2 Pro, 16GB RAM), không phải hệ thống CI/CD dùng chung cho team
ở giai đoạn này.

## 2. Goals

- Sinh testcase tự động từ tài liệu đầu vào ở nhiều dạng: text/ticket trên Redmine,
  file PDF, hoặc hình ảnh (screenshot, sơ đồ) — xuất ra file Excel để review/sửa.
- Từ testcase (sinh tự động hoặc viết tay), sinh script automation chạy thật:
  - Web: WTS, MWTS (Playwright).
  - Mobile: MTS trên Android (emulator, qua Appium + adb) và iOS (Simulator, qua
    Appium + XCUITest).
- Chạy test bằng script đã sinh, **không cần gọi AI trong lúc chạy** — tiết kiệm
  token cho các lần chạy lại (regression).
- Trong lúc chạy test mobile, thu thập được API/Socket traffic và Logcat, đính
  kèm vào report khi có lỗi để debug nhanh hơn.
- Khi gặp ca không thể xử lý bằng script tĩnh (luồng mới chưa có script, hoặc kết
  quả fail cần xác minh lại bằng mắt/suy luận), fallback sang Claude in Chrome
  (web) hoặc Claude mobile tool (Android/iOS) — chấp nhận tốn token ở đúng chỗ cần.
- Xuất report tổng hợp dạng Excel sau mỗi lần chạy (pass/fail theo từng testcase,
  theo platform, kèm log/ảnh lỗi).
- Đăng nhập test tự động bằng các account test cố định (pass, OTP mặc định), chỉ
  dừng chờ nhập tay khi task yêu cầu OTP khác mặc định.

## 3. Non-goals (chưa làm ở giai đoạn này)

- Không xây dashboard web nhiều người dùng — bắt đầu bằng CLI cho cá nhân dùng.
- Không tự động hoá lịch chạy định kỳ / tích hợp CI tập trung.
- Không thay thế hoàn toàn Claude — kiến trúc Hybrid (mục 5, phương án C) vẫn giữ
  Claude cho các ca khó, có chủ đích.
- Không tự build parser Redmine qua API ngay — vì chưa có API token (xem mục 7),
  giai đoạn đầu hỗ trợ paste/export thủ công nội dung ticket.

## 4. Anti-goals (tránh, dù kỹ thuật làm được)

- Tránh để Qwen tự "bịa" testcase lệch khỏi tài liệu gốc mà không ai review — mọi
  testcase sinh ra phải ở dạng Excel con người đọc/sửa được trước khi chạy, không
  auto-run thẳng ở giai đoạn đầu.
- Tránh chạy đồng thời Ollama (LLM) + Android emulator + iOS Simulator + nhiều
  browser instance trên máy 16GB RAM — dễ đơ máy. Thiết kế tách pha sinh
  (cần LLM) và pha chạy (không cần LLM) để không chạy cùng lúc.
- Tránh lưu bất kỳ credential nào (account, password, OTP, Redmine token) dưới
  dạng plaintext trong code hoặc trong git history.
- Tránh để `runner/` tự động login/thao tác trên một host chưa được xác nhận là
  môi trường test/UAT (xem "Safety gate" ở mục 6) — tránh nguy cơ đặt lệnh/di
  chuyển tiền thật nếu lỡ trỏ nhầm vào production.

## 5. Approaches đã cân nhắc

**A. Agentic (LLM quyết định từng bước lúc chạy):** mỗi bước test, LLM nhìn
state/màn hình hiện tại rồi quyết định hành động kế tiếp. Linh hoạt, tự xử lý
popup/UI thay đổi, nhưng nếu dùng Claude in Chrome thì tốn token Claude đều đặn ở
mọi lần chạy — không đạt mục tiêu tiết kiệm token.

**B. Scripted (sinh script một lần, chạy lại nhiều lần):** Qwen đọc testcase, sinh
script cố định (Playwright/Appium), từ đó chạy lại bao nhiêu lần tuỳ ý mà không
cần AI. Rẻ nhất, nhưng khi UI đổi, script cũ fail và cần sinh lại — không tự xử
lý được ca mới/lạ.

**C. Hybrid (đã chọn):** mặc định dùng B cho các luồng ổn định (phần lớn test
case lặp lại/regression); chỉ dùng Claude in Chrome / Claude mobile tool khi:
  1. Testcase mới chưa có script.
  2. Script B chạy fail và cần xác minh đó là bug thật hay do UI/API đổi.
  3. Test thăm dò (exploratory) theo yêu cầu đột xuất.

Lý do chọn C: cân bằng giữa tiết kiệm token (phần lớn test chạy bằng B, miễn phí)
và vẫn giữ được khả năng xử lý linh hoạt của Claude cho đúng những ca cần nó.

## 6. Kiến trúc (các quyết định về "how")

```
qwen-test-automation/
  config/             # credentials.local.json, redmine.local.json — gitignored
  ingestion/          # đọc docs (Redmine text / PDF / ảnh) -> testcase (JSON nội bộ)
  testcases/          # file Excel testcase (versioned, review/sửa tay được)
  scripts/
    web/              # Playwright script cho WTS/MWTS (sinh bởi Qwen hoặc viết tay)
    mobile/
      android/        # Appium script cho MTS trên Android emulator
      ios/            # Appium script cho MTS trên iOS Simulator
  runner/              # orchestrator: chọn script B để chạy, hoặc gọi fallback C
  capture/             # thu API/Socket traffic (mitmproxy) + logcat (adb)
  reports/             # Excel report output theo từng lần chạy
  llm/                 # wrapper gọi Ollama: generate_testcase(), generate_script()
  history.db           # SQLite, lưu lịch sử chạy (pass/fail theo thời gian)
```

**Luồng xử lý:**

1. `ingestion/` nhận input (text Redmine, PDF, ảnh) → gọi Qwen (qua `llm/`) → sinh
   testcase dạng JSON nội bộ → ghi ra Excel trong `testcases/` để review.
2. Sau khi testcase được duyệt (sửa tay nếu cần), `llm/generate_script()` sinh
   script Playwright/Appium tương ứng, lưu vào `scripts/`.
3. `runner/` chạy script đã có (B). Nếu không có script cho testcase đó, hoặc
   script fail cần xác minh, `runner/` fallback sang gọi Claude in Chrome / Claude
   mobile tool (C) cho đúng testcase đó.
4. Trong lúc chạy mobile, `capture/` ghi logcat (qua `adb logcat`) và traffic
   API/Socket (qua mitmproxy hoặc cấu hình proxy trên emulator/simulator).
5. `reports/` tổng hợp kết quả (từ `history.db` + log/ảnh lỗi) thành Excel sau
   mỗi lần chạy.

**Model Qwen:** dùng Ollama (chạy native trên Apple Silicon qua Metal). Hai vai
trò tách riêng để nhẹ máy và dễ swap model sau này:
  - Model text/code (sinh testcase, sinh script) — một bản Qwen dòng Instruct/Coder
    cỡ 7-8B, quantized (4-bit), phù hợp RAM 16GB.
  - Model vision (đọc ảnh/PDF scan có hình) — một bản Qwen-VL cùng cỡ, chỉ load khi
    cần xử lý tài liệu có ảnh.
  Chọn version cụ thể (vd Qwen3 hay Qwen2.5 dòng nào) tại thời điểm build, lấy bản
  mới nhất có sẵn trên Ollama registry lúc đó — không chốt cứng version trong thiết
  kế vì model có thể đã cập nhật.

**Safety gate (bổ sung sau builder check):** trước khi `runner/` thực hiện bất kỳ
auto-login/auto-action nào, nó kiểm tra host đích nằm trong một allowlist cấu hình
sẵn (file config, không phải hard-code) các host đã được xác nhận là test/UAT.
Host lạ/không nằm trong allowlist → `runner/` từ chối chạy, không login. Đây là
điều kiện bắt buộc trước khi build phần auto-login thật (xem mục 9).

**Cơ chế fallback sang Claude (C) — bất đồng bộ, không block run:** vì Claude in
Chrome / Claude mobile tool chỉ chạy được trong một phiên Claude Code tương tác
(không có API độc lập để một script Python gọi thẳng), `runner/` KHÔNG tự gọi
Claude. Khi một testcase cần fallback (chưa có script, hoặc fail cần xác minh),
`runner/` chỉ đánh dấu testcase đó là `pending_claude_review` trong `history.db`
và ghi vào một hàng đợi (`reports/pending_review.xlsx` hoặc tương đương), rồi
**chạy tiếp các testcase còn lại** — không đứng chờ. Sau đó, Long (hoặc một phiên
Claude Code riêng) mở hàng đợi này ra, dùng Claude in Chrome/mobile tool xử lý
từng ca, rồi ghi kết quả ngược lại vào `history.db`. Nhờ vậy một lần chạy
regression lớn vẫn hoàn thành không người canh, trừ các ca cần Claude được xử lý
sau, tách rời.

**Luật phân loại fail (failure triage, mặc định — có thể tinh chỉnh sau khi chạy
thực tế):** để quyết định một testcase fail nên báo thẳng là bug hay cần Claude
xác minh trước, `runner/` phân biệt hai loại lỗi:
  - **Lỗi cấu trúc/locator** (không tìm thấy selector, timeout chờ phần tử, script
    crash, điều hướng thất bại) → nhiều khả năng do UI/luồng đổi, không phải bug
    nghiệp vụ → đưa vào hàng đợi `pending_claude_review` để xác minh/sinh lại script.
  - **Lỗi assertion nghiệp vụ** (tìm đúng phần tử, lấy đúng giá trị, nhưng giá trị
    sai so với kỳ vọng — vd số dư, trạng thái lệnh) → báo thẳng là nghi vấn bug
    trong report, kèm retry 1 lần trước khi kết luận fail để giảm flaky.
  Đây là luật mặc định ban đầu; QA có thể chỉnh lại sau khi thấy kết quả thật.

**Tách pha để không đơ máy (anti-goal mục 4):** Ollama cấu hình auto-unload model
sau khi idle, để khi `runner/` chạy emulator/simulator/browser thì RAM không bị
LLM chiếm giữ.

**Stack:** Python (venv riêng, không dùng chung Python hệ thống 3.9.6 — builder tự
chọn version Python cụ thể khi setup) để có một ngôn ngữ xuyên suốt, tận dụng
`openpyxl`/`pandas` (Excel), `pdfplumber`/`PyMuPDF` (đọc PDF), `Appium-Python-Client`,
`playwright` (Python binding — máy đã có Playwright qua npx, builder quyết định
dùng binding Python hay giữ Node tuỳ mức tiện lợi lúc code), `requests` (gọi Ollama
REST API và Redmine API).

**Quản lý credential:** 8 account test (số tài khoản, password, OTP mặc định) lưu
trong `config/credentials.local.json`, nằm trong `.gitignore`, không bao giờ xuất
hiện trong code hay trong Excel report. `runner/` đọc file này lúc login. Khi một
task cụ thể cần OTP khác mặc định, `runner/` dừng và chờ nhập tay cho đúng lần
chạy đó, không lưu OTP đó lại.

## 7. Constraints

- Máy: Apple M2 Pro, 16GB RAM — giới hạn size model Qwen chạy được đồng thời với
  emulator/simulator; vì vậy tách pha sinh và pha chạy (mục 6).
- Công cụ đã có sẵn trên máy, không cần cài thêm trừ Ollama: `adb`
  (Android SDK tại `~/Library/Android/sdk`), Appium, Xcode + iOS Simulator,
  Playwright (qua npx).
- Redmine: cần API token để tự động kéo ticket — **chưa có lúc viết thiết kế này**.
  Giai đoạn đầu `ingestion/` hỗ trợ nhận text paste/export thủ công từ Redmine;
  bổ sung gọi API thật khi có token (xem mục 9).
- Đây là git worktree riêng (`claude/local-qwen-llm-automation-0ab021`) trong repo
  vốn là backup Claude skills của Shinhan — không liên quan tới nội dung repo gốc,
  nên code của project này nên nằm gọn trong thư mục `qwen-test-automation/` để
  không lẫn với phần backup skill.

## 8. Việc để builder tự quyết (không cần hỏi lại user)

- Version Python cụ thể, version các thư viện.
- Format chi tiết JSON testcase nội bộ (trước khi xuất Excel).
- Cách chia sheet trong file Excel report (1 sheet tổng quan + n sheet chi tiết
  theo platform WTS/MWTS/MTS-Android/MTS-iOS).
- Dùng Playwright Python binding hay gọi qua Node — miễn đạt được mục tiêu chạy
  Playwright test không cần AI.
- Version cụ thể của model Qwen (text và vision) lấy tại thời điểm build.

## 9. Việc còn mở, cần xác nhận/bổ sung trước khi build phần liên quan (chưa chặn thiết kế tổng thể)

- ~~Xác nhận WTS/MWTS/MTS test trỏ vào môi trường UAT/sandbox~~ — **đã xác nhận
  (2026-11-20): đúng là UAT an toàn, không đặt lệnh/di chuyển tiền thật.** Vẫn
  cần danh sách host/URL cụ thể (xem mục bên dưới) để đưa vào allowlist của
  safety gate (mục 6) lúc build.
- ~~App MTS có bật certificate pinning không?~~ — **đã xác nhận (2026-11-20):
  không pin.** Giữ nguyên hướng dùng `mitmproxy` cho module `capture/` như thiết
  kế ban đầu ở mục 6, không cần Frida/unpinning.
- Redmine API token — khi có, bổ sung để `ingestion/` tự kéo ticket thay vì paste
  tay.
- URL/host thật của WTS và MWTS.
- Nguồn file cài MTS (APK cho Android emulator, IPA/build cho iOS Simulator).
- Ý nghĩa/khác biệt giữa 8 account test (có account nào dành riêng cho tính năng
  gì không, hay dùng account nào cũng được) — không chặn thiết kế, nhưng cần biết
  lúc viết testcase cụ thể.
