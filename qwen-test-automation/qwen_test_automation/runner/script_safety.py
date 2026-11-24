import re
from urllib.parse import urlparse

from qwen_test_automation.config.host_allowlist import is_host_allowed
from qwen_test_automation.runner.safety_gate import HostNotAllowedError

_URL_PATTERN = re.compile(r"https?://[^\s'\"]+")
# Qwen coder models often preface or follow a fenced code block with a
# plain-English sentence even when told not to ("Here's a Python script
# that..."), so the fence isn't always the first/last thing in the
# response. Find a ```...``` block anywhere and keep only its contents.
_FENCE_PATTERN = re.compile(r"```(?:[A-Za-z0-9_+-]*\n)?(.*?)```", re.DOTALL)


class ScriptCompileError(Exception):
    pass


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    match = _FENCE_PATTERN.search(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def assert_script_compiles(source: str) -> None:
    try:
        compile(source, "<generated-script>", "exec")
    except SyntaxError as e:
        raise ScriptCompileError(f"generated script does not compile: {e}") from e


def assert_script_hosts_allowed(source: str, allowed_hosts: set) -> None:
    for match in _URL_PATTERN.findall(source):
        host = urlparse(match).hostname
        if not is_host_allowed(host, allowed_hosts):
            raise HostNotAllowedError(
                f"script references a host not in allowlist, refusing to run: {host} (from {match!r})"
            )
