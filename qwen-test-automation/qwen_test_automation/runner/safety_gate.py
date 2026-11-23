from urllib.parse import urlparse

from qwen_test_automation.config.host_allowlist import is_host_allowed


class HostNotAllowedError(Exception):
    pass


def assert_host_allowed(url: str, allowed_hosts: set) -> None:
    host = urlparse(url).hostname
    if not is_host_allowed(host, allowed_hosts):
        raise HostNotAllowedError(f"host not in allowlist, refusing to run: {host} (from {url})")
