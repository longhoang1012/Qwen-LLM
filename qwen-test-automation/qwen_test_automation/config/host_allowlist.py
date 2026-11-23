import json


class HostAllowlistError(Exception):
    pass


def load_allowed_hosts(path: str) -> set:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return set()
    except OSError as e:
        raise HostAllowlistError(f"host allowlist file could not be read: {path} ({e})") from e

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise HostAllowlistError(f"host allowlist file has invalid JSON: {path}") from e

    if not isinstance(parsed, list) or not all(
        isinstance(host, str) and host for host in parsed
    ):
        raise HostAllowlistError(
            f"host allowlist file must be a JSON array of non-empty host strings: {path}"
        )

    return set(parsed)


def is_host_allowed(host: str, allowed_hosts: set) -> bool:
    return host in allowed_hosts
