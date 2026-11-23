import os
import subprocess
import sys


class ExecutionTimeoutError(Exception):
    pass


class ExecutionResult:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_script(script_path: str, timeout: int = 60, env: dict = None) -> ExecutionResult:
    full_env = {**os.environ, **(env or {})}
    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=full_env,
        )
    except subprocess.TimeoutExpired as e:
        raise ExecutionTimeoutError(
            f"script did not finish within {timeout}s: {script_path}"
        ) from e

    return ExecutionResult(proc.returncode, proc.stdout, proc.stderr)
