from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from utils.cli_sessions import _resolve_python_executable


def call_python_function(
    module: str,
    function: str,
    args: Optional[list] = None,
    kwargs: Optional[dict] = None,
    conda_env: Optional[str] = None,
    workdir: Optional[str] = None,
    timeout_ms: int = 5000,
    capture_stdout: bool = True,
) -> Dict[str, Any]:
    """Invoke a Python function in a separate process and return structured results.

    Spawns the configured Python (optionally via conda env) to run utils.function_runner
    with a JSON payload via stdin. Enforces a hard timeout.
    """
    payload = {
        "module": module,
        "function": function,
        "args": args or [],
        "kwargs": kwargs or {},
        "workdir": str(workdir or Path.cwd()),
        "capture_stdout": bool(capture_stdout),
    }
    pyexec = _resolve_python_executable(conda_env)
    if pyexec.startswith("conda:run:-n:"):
        envname = pyexec.split(":")[-1]
        executable = "conda"
        argv = ["run", "-n", envname, "python", "-u", "-m", "utils.function_runner"]
    else:
        executable = pyexec
        argv = ["-u", "-m", "utils.function_runner"]
    try:
        proc = subprocess.run(
            [executable] + argv,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=workdir or None,
            timeout=max(0.1, float(timeout_ms) / 1000.0),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "result": None,
            "stdout": "",
            "stderr": "",
            "error_type": "Timeout",
            "error_message": f"Function call exceeded {timeout_ms} ms",
            "traceback": None,
        }
    # If the runner failed to start at the OS level
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    try:
        data = json.loads(stdout or "{}")
        # Ensure required fields
        if not isinstance(data, dict) or "ok" not in data:
            raise ValueError("Malformed runner output")
        return data
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "result": None,
            "stdout": stdout,
            "stderr": stderr,
            "error_type": "RunnerError",
            "error_message": str(exc),
            "traceback": None,
        }


__all__ = ["call_python_function"]

