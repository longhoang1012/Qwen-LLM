import json

import pytest

from qwen_test_automation.config.host_allowlist import (
    load_allowed_hosts,
    is_host_allowed,
    HostAllowlistError,
)


def test_missing_file_defaults_to_deny_all(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    assert load_allowed_hosts(str(missing)) == set()


def test_load_allowed_hosts_from_file(tmp_path):
    p = tmp_path / "host_allowlist.json"
    p.write_text(json.dumps(["uat-wts.shinhan.internal"]))
    assert load_allowed_hosts(str(p)) == {"uat-wts.shinhan.internal"}


def test_malformed_file_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("[not valid")
    with pytest.raises(HostAllowlistError, match="invalid JSON"):
        load_allowed_hosts(str(p))


def test_load_allowed_hosts_raises_when_not_a_list(tmp_path):
    p = tmp_path / "not_a_list.json"
    p.write_text(json.dumps({"hosts": ["uat-wts.shinhan.internal"]}))
    with pytest.raises(HostAllowlistError, match="JSON array"):
        load_allowed_hosts(str(p))


def test_load_allowed_hosts_raises_when_items_not_strings(tmp_path):
    p = tmp_path / "bad_items.json"
    p.write_text(json.dumps([["uat-wts.shinhan.internal"]]))
    with pytest.raises(HostAllowlistError, match="JSON array"):
        load_allowed_hosts(str(p))


def test_is_host_allowed_true_and_false():
    allowed = {"uat-wts.shinhan.internal"}
    assert is_host_allowed("uat-wts.shinhan.internal", allowed) is True
    assert is_host_allowed("prod-wts.shinhan.com", allowed) is False
