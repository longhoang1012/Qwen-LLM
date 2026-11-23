from qwen_test_automation.runner.script_store import (
    script_path_for,
    load_script,
    save_script,
)


def test_load_script_missing_returns_none(tmp_path):
    assert load_script("TC-001", str(tmp_path / "scripts")) is None


def test_save_then_load_round_trips(tmp_path):
    scripts_dir = str(tmp_path / "scripts")
    path = save_script("TC-001", "print('hello')", scripts_dir)
    assert path == script_path_for("TC-001", scripts_dir)
    assert load_script("TC-001", scripts_dir) == "print('hello')"


def test_save_script_creates_missing_directory(tmp_path):
    scripts_dir = str(tmp_path / "does" / "not" / "exist")
    save_script("TC-001", "print('hi')", scripts_dir)
    assert load_script("TC-001", scripts_dir) == "print('hi')"
