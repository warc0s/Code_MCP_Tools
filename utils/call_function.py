from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from utils.cli_sessions import _resolve_python_executable

_ALLOWED_MODULE_PREFIXES = ("utils", "utils.", "scripts", "scripts.")
_MODULE_RE = re.compile(r"[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*")
_FUNCTION_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _is_under_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False


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
    module_name = (module or "").strip()
    function_name = (function or "").strip()
    if not module_name or not _MODULE_RE.fullmatch(module_name):
        raise ValueError("Invalid module name.")
    if not function_name or not _FUNCTION_RE.fullmatch(function_name):
        raise ValueError("Invalid function name.")
    if function_name.startswith("__"):
        raise ValueError("Dunder functions are not allowed.")
    if not module_name.startswith(_ALLOWED_MODULE_PREFIXES):
        raise ValueError("Module not allowed. Allowed prefixes: utils.*, scripts.*")

    repo_root = Path.cwd().resolve()
    workdir_arg = (workdir or ".").strip()
    if not workdir_arg:
        workdir_arg = "."
    candidate = Path(workdir_arg)
    workdir_abs = candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()
    if not _is_under_root(workdir_abs, repo_root):
        raise ValueError("workdir outside repository.")

    payload = {
        "module": module_name,
        "function": function_name,
        "args": args or [],
        "kwargs": kwargs or {},
        "workdir": str(workdir_abs),
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
        input_payload = json.dumps(payload)
    except (TypeError, ValueError) as exc:
        return {
            "ok": False,
            "result": None,
            "stdout": "",
            "stderr": "",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": None,
        }
    try:
        proc = subprocess.run(
            [executable] + argv,
            input=input_payload,
            text=True,
            capture_output=True,
            cwd=workdir_abs.as_posix(),
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
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "result": None,
            "stdout": "",
            "stderr": "",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
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
