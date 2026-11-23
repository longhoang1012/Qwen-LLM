import json


class CredentialsError(Exception):
    pass


def load_credentials(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        raise CredentialsError(f"credentials file not found: {path}")
    except OSError as e:
        raise CredentialsError(f"credentials file could not be read: {path} ({e})") from e

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise CredentialsError(f"credentials file has invalid JSON: {path}") from e

    if not isinstance(parsed, dict):
        raise CredentialsError(
            f"credentials file must be a JSON object mapping account -> "
            f"{{password, default_otp}}: {path}"
        )

    for account, entry in parsed.items():
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("password"), str)
            or not isinstance(entry.get("default_otp"), str)
        ):
            raise CredentialsError(
                f"credentials entry for account {account!r} must have string "
                f"'password' and 'default_otp': {path}"
            )

    return parsed
