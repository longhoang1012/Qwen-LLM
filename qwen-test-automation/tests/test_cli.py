import pytest

import json

from qwen_test_automation.models import TestScenario
from qwen_test_automation.history.db import init_db
from qwen_test_automation.runner.script_store import save_script, load_script
from qwen_test_automation.runner.safety_gate import HostNotAllowedError
from qwen_test_automation.config.credentials import CredentialsError
from cli import _generate_scripts, _run_tests, _resolve_credentials, _require_nonempty_allowlist

ALLOWED = {"uat.example.internal"}
URL = "https://uat.example.internal"


class FakeClient:
    def __init__(self, response_text):
        self.response_text = response_text

    def generate(self, model, prompt, images=None):
        return self.response_text


class SequencedFakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate(self, model, prompt, images=None):
        resp = self.responses[self.calls]
        self.calls += 1
        return resp


def make_scenario(id_="SC-001", applicable_platforms=("WTS", "MWTS")):
    return TestScenario(
        id=id_, feature="Đăng nhập", group="Xác thực", screen="Login",
        title="Đăng nhập với OTP đúng", precondition="Tài khoản tồn tại",
        steps=["Mở trang đăng nhập", "Nhập OTP"],
        expected_result="Vào được trang chủ",
        applicable_platforms=list(applicable_platforms),
    )


def test_generate_scripts_writes_one_script_per_applicable_web_platform(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = FakeClient("import sys\nsys.exit(0)\n")
    results = _generate_scripts([make_scenario()], scripts_dir, ALLOWED, client, "m")
    ids = [r[0] for r in results]
    assert ids == ["SC-001-WTS", "SC-001-MWTS"]
    assert load_script("SC-001-WTS", scripts_dir) is not None
    assert load_script("SC-001-MWTS", scripts_dir) is not None


def test_generate_scripts_reports_mobile_skip(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = FakeClient("import sys\nsys.exit(0)\n")
    scenario = make_scenario(applicable_platforms=("WTS", "MTS-Android"))
    results = _generate_scripts([scenario], scripts_dir, ALLOWED, client, "m")
    ids_and_statuses = {r[0]: r[1] for r in results}
    assert ids_and_statuses["SC-001-MTS-Android"] == "skipped_unsupported_platform"
    assert "SC-001-WTS" in ids_and_statuses
    assert ids_and_statuses["SC-001-WTS"] != "skipped_unsupported_platform"


def test_generate_scripts_isolates_compile_error_per_testcase(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = FakeClient("def f(:\n")  # invalid syntax
    scenario = make_scenario(applicable_platforms=("WTS", "MWTS"))
    results = _generate_scripts([scenario], scripts_dir, ALLOWED, client, "m")
    ids = [r[0] for r in results]
    assert ids == ["SC-001-WTS", "SC-001-MWTS"]
    assert all(status.startswith("error:") for _, status in results)


def test_generate_scripts_isolates_host_error_per_testcase(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = FakeClient("page.goto('https://prod.evil.com/login')\n")
    scenario = make_scenario(applicable_platforms=("WTS",))
    results = _generate_scripts([scenario], scripts_dir, ALLOWED, client, "m")
    assert results[0][0] == "SC-001-WTS"
    assert results[0][1].startswith("error:")


def test_generate_scripts_continues_after_one_scenario_errors(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    client = SequencedFakeClient(["def f(:\n", "import sys\nsys.exit(0)\n"])
    bad = make_scenario(id_="SC-BAD", applicable_platforms=("WTS",))
    good = make_scenario(id_="SC-GOOD", applicable_platforms=("WTS",))
    results = _generate_scripts([bad, good], scripts_dir, ALLOWED, client, "m")
    assert results[0][0] == "SC-BAD-WTS" and results[0][1].startswith("error:")
    assert results[1][0] == "SC-GOOD-WTS" and not results[1][1].startswith("error:")


def test_run_tests_runs_each_applicable_web_platform(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    save_script("SC-001-WTS", "import sys\nsys.exit(0)\n", scripts_dir)
    save_script("SC-001-MWTS", "import sys\nsys.exit(1)\n", scripts_dir)
    conn = init_db(str(tmp_path / "h.db"))
    results = _run_tests([make_scenario()], URL, ALLOWED, scripts_dir, conn)
    assert ("SC-001-WTS", "pass") in results
    assert ("SC-001-MWTS", "pending_claude_review") in results


def test_run_tests_records_skip_for_mobile_platform(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    conn = init_db(str(tmp_path / "h.db"))
    scenario = make_scenario(applicable_platforms=("MTS-Android",))
    results = _run_tests([scenario], URL, ALLOWED, scripts_dir, conn)
    assert results == [("SC-001-MTS-Android", "skipped_unsupported_platform")]


def test_run_tests_raises_immediately_on_disallowed_host(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    conn = init_db(str(tmp_path / "h.db"))
    with pytest.raises(HostNotAllowedError):
        _run_tests([make_scenario()], "https://prod.evil.com", ALLOWED, scripts_dir, conn)


# --- credentials / allowlist CLI validation helpers ---

def test_resolve_credentials_returns_none_when_no_account():
    assert _resolve_credentials("irrelevant/path.json", None) is None


def test_resolve_credentials_raises_clear_error_on_missing_file(tmp_path):
    with pytest.raises(CredentialsError):
        _resolve_credentials(str(tmp_path / "missing.json"), "acc1")


def test_resolve_credentials_raises_value_error_on_unknown_account(tmp_path):
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"0000000001": {"password": "x", "default_otp": "000000"}}))
    with pytest.raises(ValueError, match="acc1"):
        _resolve_credentials(str(p), "acc1")


def test_resolve_credentials_returns_dict_for_known_account(tmp_path):
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"0000000001": {"password": "x", "default_otp": "000000"}}))
    result = _resolve_credentials(str(p), "0000000001")
    assert result == {"0000000001": {"password": "x", "default_otp": "000000"}}


def test_require_nonempty_allowlist_raises_on_missing_file(tmp_path):
    with pytest.raises(ValueError, match="allowlist"):
        _require_nonempty_allowlist(str(tmp_path / "missing.json"))


def test_require_nonempty_allowlist_returns_hosts_when_present(tmp_path):
    p = tmp_path / "allowlist.json"
    p.write_text(json.dumps(["uat.example.internal"]))
    assert _require_nonempty_allowlist(str(p)) == {"uat.example.internal"}
