import argparse
import os

from qwen_test_automation.models import to_testcase
from qwen_test_automation.llm.ollama_client import OllamaClient
from qwen_test_automation.config.credentials import load_credentials, CredentialsError
from qwen_test_automation.config.host_allowlist import load_allowed_hosts
from qwen_test_automation.history.db import init_db
from qwen_test_automation.ingestion.pipeline import run_ingestion
from qwen_test_automation.ingestion.excel_import import read_scenarios_from_excel
from qwen_test_automation.reporting.final_report import write_final_report
from qwen_test_automation.runner.safety_gate import HostNotAllowedError
from qwen_test_automation.runner.script_safety import ScriptCompileError
from qwen_test_automation.runner.script_store import load_script
from qwen_test_automation.runner.web_runner import ensure_script_generated, run_web_testcase


def _generate_scripts(scenarios, scripts_dir, allowed_hosts, client, model, supported_platforms=("WTS", "MWTS")):
    results = []
    for scenario in scenarios:
        for platform in scenario.applicable_platforms:
            testcase = to_testcase(scenario, platform)
            if platform not in supported_platforms:
                results.append((testcase.id, "skipped_unsupported_platform"))
                continue
            # Checked before calling ensure_script_generated (which itself
            # returns an existing script's path unchanged) so the caller
            # can tell "generated now" from "reused from a previous run" —
            # otherwise a second document whose LLM-chosen testcase ids
            # happen to collide with an earlier one silently keeps running
            # the earlier script while being reported as freshly generated.
            already_existed = load_script(testcase.id, scripts_dir) is not None
            try:
                path = ensure_script_generated(testcase, client, model, scripts_dir, allowed_hosts)
            except (ScriptCompileError, HostNotAllowedError) as e:
                results.append((testcase.id, f"error: {e}"))
                continue
            label = "reused" if already_existed else "generated"
            results.append((testcase.id, f"{label}: {path}"))
    return results


def _run_tests(scenarios, url, allowed_hosts, scripts_dir, conn, credentials=None, account=None, timeout=60, supported_platforms=("WTS", "MWTS")):
    results = []
    for scenario in scenarios:
        for platform in scenario.applicable_platforms:
            testcase = to_testcase(scenario, platform)
            if platform not in supported_platforms:
                results.append((testcase.id, "skipped_unsupported_platform"))
                continue
            status = run_web_testcase(
                testcase, url, allowed_hosts, scripts_dir, conn,
                credentials=credentials, account=account, timeout=timeout,
            )
            results.append((testcase.id, status))
    return results


def _resolve_credentials(credentials_path, account):
    """Returns the credentials dict for `account`, or None if `account`
    is None. Raises CredentialsError on a missing/malformed file, or
    ValueError naming the account if it isn't in the file — both with a
    clear message, so the CLI never has to guess which account exists."""
    if account is None:
        return None
    credentials = load_credentials(credentials_path)
    if account not in credentials:
        raise ValueError(f"account {account!r} không có trong {credentials_path}")
    return credentials


def _require_nonempty_allowlist(host_allowlist_path):
    """Returns the host allowlist, or raises a clear ValueError if it's
    missing or empty — rather than silently deny-all-ing every run with
    no hint why."""
    allowed_hosts = load_allowed_hosts(host_allowlist_path)
    if not allowed_hosts:
        raise ValueError(
            f"host allowlist trống hoặc chưa tồn tại: {host_allowlist_path} "
            f"— tạo file này từ config_examples/host_allowlist.local.json.example trước khi chạy"
        )
    return allowed_hosts


def _default_report_path(testcases_xlsx):
    base, ext = os.path.splitext(testcases_xlsx)
    return f"{base}_report{ext}"


def _print_generate_results(results):
    reused_count = 0
    for testcase_id, result in results:
        if result == "skipped_unsupported_platform":
            print(f"{testcase_id}: bỏ qua (nền tảng mobile chưa được CLI này hỗ trợ)")
        elif isinstance(result, str) and result.startswith("error:"):
            print(f"{testcase_id}: {result}")
        elif isinstance(result, str) and result.startswith("reused:"):
            path = result[len("reused:"):].strip()
            print(f"{testcase_id}: dùng lại script có sẵn {path} (CHƯA sinh mới — nếu đây là tài liệu khác, kiểm tra script này còn đúng không)")
            reused_count += 1
        elif isinstance(result, str) and result.startswith("generated:"):
            path = result[len("generated:"):].strip()
            print(f"Generated {path} for {testcase_id} — review before running")
        else:
            print(f"{testcase_id}: {result}")
    if reused_count:
        print(f"\nLưu ý: {reused_count} testcase dùng lại script đã có sẵn trong scripts-dir (không sinh mới).")


def main():
    parser = argparse.ArgumentParser(prog="cli.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser(
        "generate-scenarios",
        help="Đọc 1 file (PDF/txt/md/ảnh) và sinh testcase Excel theo chuẩn QC",
    )
    gen.add_argument("doc_path", help="Đường dẫn file đầu vào (.pdf/.txt/.md/.png/.jpg/.jpeg)")
    gen.add_argument("out_path", help="Đường dẫn file Excel sẽ ghi ra")
    gen.add_argument("--text-model", default="qwen2.5:7b")
    gen.add_argument("--vision-model", default="qwen2.5vl:7b")
    gen.add_argument("--ollama-url", default="http://localhost:11434")
    gen.add_argument(
        "--timeout", type=int, default=120,
        help="Số giây chờ Ollama trả lời trước khi báo timeout (mặc định 120)",
    )

    genscript = subparsers.add_parser(
        "generate-script",
        help="Sinh script automation cho các testcase trong file Excel (chỉ sinh, không chạy)",
    )
    genscript.add_argument("testcases_xlsx", help="File Excel testcase đã review")
    genscript.add_argument("--scripts-dir", default="scripts")
    genscript.add_argument("--host-allowlist", default="config_local/host_allowlist.json")
    genscript.add_argument("--text-model", default="qwen2.5-coder:7b")
    genscript.add_argument("--ollama-url", default="http://localhost:11434")
    genscript.add_argument("--timeout", type=int, default=120)

    prepare = subparsers.add_parser(
        "prepare-tests",
        help="Gộp generate-scenarios + generate-script: docs -> testcase Excel -> script, "
             "vẫn chỉ sinh, không chạy gì",
    )
    prepare.add_argument("doc_path", help="Đường dẫn file đầu vào (.pdf/.txt/.md/.png/.jpg/.jpeg)")
    prepare.add_argument("out_path", help="Đường dẫn file Excel testcase sẽ ghi ra")
    prepare.add_argument("--scripts-dir", default="scripts")
    prepare.add_argument("--host-allowlist", default="config_local/host_allowlist.json")
    prepare.add_argument("--text-model", default="qwen2.5:7b")
    prepare.add_argument("--vision-model", default="qwen2.5vl:7b")
    prepare.add_argument("--script-model", default="qwen2.5-coder:7b")
    prepare.add_argument("--ollama-url", default="http://localhost:11434")
    prepare.add_argument("--timeout", type=int, default=120)

    runtests = subparsers.add_parser(
        "run-tests",
        help="Chạy các script đã sinh/đã review trong scripts-dir (không tự sinh script mới)",
    )
    runtests.add_argument("testcases_xlsx", help="File Excel testcase đã review")
    runtests.add_argument("--scripts-dir", default="scripts")
    runtests.add_argument("--host-allowlist", default="config_local/host_allowlist.json")
    runtests.add_argument("--credentials", default="config_local/credentials.json")
    runtests.add_argument("--url", required=True)
    runtests.add_argument("--account", default=None)
    runtests.add_argument("--history-db", default="history.db")
    runtests.add_argument("--timeout", type=int, default=60)
    runtests.add_argument(
        "--report", default=None,
        help="Đường dẫn report cuối (mặc định: <file input>_report.xlsx)",
    )

    args = parser.parse_args()

    if args.command == "generate-scenarios":
        client = OllamaClient(base_url=args.ollama_url, timeout=args.timeout)
        scenarios = run_ingestion(
            args.doc_path, args.out_path, client,
            text_model=args.text_model, vision_model=args.vision_model,
        )
        print(f"Wrote {len(scenarios)} scenario(s) to {args.out_path}")

    elif args.command == "generate-script":
        try:
            allowed_hosts = _require_nonempty_allowlist(args.host_allowlist)
        except ValueError as e:
            print(f"Lỗi: {e}")
            return
        client = OllamaClient(base_url=args.ollama_url, timeout=args.timeout)
        scenarios = read_scenarios_from_excel(args.testcases_xlsx)
        results = _generate_scripts(scenarios, args.scripts_dir, allowed_hosts, client, args.text_model)
        _print_generate_results(results)
        print(f"Done: {len(results)} testcase(s) processed in {args.scripts_dir}/")

    elif args.command == "prepare-tests":
        try:
            allowed_hosts = _require_nonempty_allowlist(args.host_allowlist)
        except ValueError as e:
            print(f"Lỗi: {e}")
            return
        client = OllamaClient(base_url=args.ollama_url, timeout=args.timeout)
        scenarios = run_ingestion(
            args.doc_path, args.out_path, client,
            text_model=args.text_model, vision_model=args.vision_model,
        )
        print(f"Đã sinh {len(scenarios)} testcase vào {args.out_path}")
        results = _generate_scripts(scenarios, args.scripts_dir, allowed_hosts, client, args.script_model)
        _print_generate_results(results)
        print(f"\nĐã sinh {len(results)} script vào {args.scripts_dir}/.")
        print(f"Review {args.out_path} và các file trong {args.scripts_dir}/ trước khi chạy.")
        print(f"Khi sẵn sàng: python cli.py run-tests {args.out_path} --url <host> --account <account>")

    elif args.command == "run-tests":
        try:
            allowed_hosts = _require_nonempty_allowlist(args.host_allowlist)
            credentials = _resolve_credentials(args.credentials, args.account)
        except (ValueError, CredentialsError) as e:
            print(f"Lỗi: {e}")
            return
        if args.account is None:
            print("Lưu ý: chưa chỉ định --account — các testcase cần đăng nhập có thể fail vì thiếu credential.")
        conn = init_db(args.history_db)
        scenarios = read_scenarios_from_excel(args.testcases_xlsx)
        try:
            results = _run_tests(
                scenarios, args.url, allowed_hosts, args.scripts_dir, conn,
                credentials=credentials, account=args.account, timeout=args.timeout,
            )
        except HostNotAllowedError as e:
            print(f"Lỗi: {e}")
            return
        counts = {}
        for testcase_id, status in results:
            print(f"{testcase_id}: {status}")
            counts[status] = counts.get(status, 0) + 1
        print(f"Tổng kết: {counts}")

        report_path = args.report or _default_report_path(args.testcases_xlsx)
        write_final_report(scenarios, conn, report_path)
        print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
