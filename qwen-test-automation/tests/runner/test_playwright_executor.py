import pytest

from qwen_test_automation.runner.playwright_executor import (
    run_script,
    ExecutionTimeoutError,
)


def test_run_script_success(tmp_path):
    p = tmp_path / "ok.py"
    p.write_text("import sys\nsys.exit(0)\n")
    result = run_script(str(p))
    assert result.returncode == 0


def test_run_script_failure_captures_stderr(tmp_path):
    p = tmp_path / "bad.py"
    p.write_text("assert False, 'boom'\n")
    result = run_script(str(p))
    assert result.returncode != 0
    assert "boom" in result.stderr


def test_run_script_passes_extra_env_vars(tmp_path):
    p = tmp_path / "env_check.py"
    p.write_text(
        "import os, sys\n"
        "sys.exit(0 if os.environ.get('MY_VAR') == 'hello' else 1)\n"
    )
    result = run_script(str(p), env={"MY_VAR": "hello"})
    assert result.returncode == 0


def test_run_script_raises_on_timeout(tmp_path):
    p = tmp_path / "slow.py"
    p.write_text("import time\ntime.sleep(5)\n")
    with pytest.raises(ExecutionTimeoutError):
        run_script(str(p), timeout=1)
