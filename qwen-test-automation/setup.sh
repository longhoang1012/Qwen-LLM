#!/usr/bin/env bash
# Setup script for qwen-test-automation.
#
# Usage:
#   ./setup.sh            # Python venv + Ollama + models (no Playwright)
#   ./setup.sh --with-browser   # also install Playwright + Chromium (~300MB)
#
# Safe to re-run — every step skips work that's already done.

set -euo pipefail
cd "$(dirname "$0")"

WITH_BROWSER=0
for arg in "$@"; do
  case "$arg" in
    --with-browser) WITH_BROWSER=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

echo "== 1/5: Python venv + dependencies =="
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
echo "OK"

echo
echo "== 2/5: Ollama =="
if ! command -v ollama >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew install ollama
  else
    echo "Không tìm thấy Homebrew. Cài Ollama thủ công: https://ollama.com/download" >&2
    exit 1
  fi
else
  echo "Ollama đã cài."
fi

# Make sure the Ollama server is actually running (needed for model pulls
# and for OllamaClient to connect later).
if ! curl -s -o /dev/null --max-time 2 http://localhost:11434; then
  if command -v brew >/dev/null 2>&1; then
    brew services start ollama >/dev/null 2>&1 || true
  fi
  # brew services can take a moment to come up; fall back to running it
  # directly in the background if it's still not listening.
  sleep 2
  if ! curl -s -o /dev/null --max-time 2 http://localhost:11434; then
    nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
    sleep 2
  fi
fi
echo "Ollama server: $(curl -s -o /dev/null --max-time 2 http://localhost:11434 && echo "đang chạy" || echo "CHƯA chạy được — kiểm tra /tmp/ollama-serve.log")"

echo
echo "== 3/5: Model Qwen (có thể mất vài phút lần đầu) =="
ollama pull qwen2.5:7b        # sinh testcase (generate-scenarios/prepare-tests)
ollama pull qwen2.5vl:7b      # đọc ảnh/PDF scan
ollama pull qwen2.5-coder:7b  # sinh script (generate-script/prepare-tests)
echo "OK"

echo
echo "== 4/5: config_local/ (credentials + host allowlist) =="
mkdir -p config_local
if [ ! -f config_local/credentials.json ]; then
  cp config_examples/credentials.local.json.example config_local/credentials.json
  echo "Đã tạo config_local/credentials.json từ file mẫu — MỞ FILE NÀY VÀ ĐIỀN GIÁ TRỊ THẬT."
else
  echo "config_local/credentials.json đã có, giữ nguyên."
fi
if [ ! -f config_local/host_allowlist.json ]; then
  cp config_examples/host_allowlist.local.json.example config_local/host_allowlist.json
  echo "Đã tạo config_local/host_allowlist.json từ file mẫu — MỞ FILE NÀY VÀ ĐIỀN HOST UAT THẬT."
else
  echo "config_local/host_allowlist.json đã có, giữ nguyên."
fi

echo
echo "== 5/5: Playwright (chạy test thật trên browser) =="
if [ "$WITH_BROWSER" = "1" ]; then
  .venv/bin/pip install -q playwright
  .venv/bin/playwright install chromium
  echo "OK"
else
  echo "Bỏ qua (chạy lại với --with-browser nếu cần chạy test thật trên WTS/MWTS)."
fi

echo
echo "== Xong =="
echo "Thử ngay:"
echo "  source .venv/bin/activate"
echo "  python cli.py generate-scenarios <file_tai_lieu> testcases/ra.xlsx"
