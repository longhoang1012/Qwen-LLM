import os


def script_path_for(testcase_id: str, scripts_dir: str) -> str:
    return os.path.join(scripts_dir, f"{testcase_id}.py")


def load_script(testcase_id: str, scripts_dir: str):
    path = script_path_for(testcase_id, scripts_dir)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_script(testcase_id: str, source: str, scripts_dir: str) -> str:
    os.makedirs(scripts_dir, exist_ok=True)
    path = script_path_for(testcase_id, scripts_dir)
    with open(path, "w", encoding="utf-8") as f:
        f.write(source)
    return path
