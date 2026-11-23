import re
from urllib.parse import urlparse

from qwen_test_automation.config.host_allowlist import is_host_allowed
from qwen_test_automation.runner.safety_gate import HostNotAllowedError

_URL_PATTERN = re.compile(r"https?://[^\s'\"]+")


class ScriptCompileError(Exception):
    pass


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


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
