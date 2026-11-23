import json

import pytest

from qwen_test_automation.config.credentials import load_credentials, CredentialsError


def test_load_credentials_returns_mapping(tmp_path):
    p = tmp_path / "credentials.json"
    p.write_text(json.dumps({
        "0000000001": {"password": "x", "default_otp": "000000"}
    }))
    creds = load_credentials(str(p))
    assert creds["0000000001"]["default_otp"] == "000000"


def test_load_credentials_missing_file_raises_actionable_error(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(CredentialsError, match="not found"):
        load_credentials(str(missing))


def test_load_credentials_malformed_json_raises_actionable_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    with pytest.raises(CredentialsError, match="invalid JSON"):
        load_credentials(str(p))


def test_load_credentials_raises_when_not_a_mapping(tmp_path):
    p = tmp_path / "list.json"
    p.write_text(json.dumps(["0000000001"]))
    with pytest.raises(CredentialsError, match="JSON object"):
        load_credentials(str(p))


def test_load_credentials_raises_when_entry_missing_fields(tmp_path):
    p = tmp_path / "bad_entry.json"
    p.write_text(json.dumps({"0000000001": {"default_otp": "000000"}}))
    with pytest.raises(CredentialsError, match="password"):
        load_credentials(str(p))
