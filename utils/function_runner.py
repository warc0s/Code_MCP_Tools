from __future__ import annotations

"""
Minimal runner to import and call a Python function by module and name.
Reads a JSON payload from stdin and writes a JSON result to stdout.

Payload schema:
{
  "module": "pkg.mod",
  "function": "callable",
  "args": [],
  "kwargs": {},
  "workdir": "optional path",
  "capture_stdout": true
}
"""

import importlib
import io
import json
import os
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import Any


def _json_safe(obj: Any):
    try:
        json.dumps(obj)
        return True
    except Exception:
        return False


def main() -> None:
    try:
        data = sys.stdin.read()
        payload = json.loads(data or "{}")
        module_name = str(payload.get("module") or "").strip()
        func_name = str(payload.get("function") or "").strip()
        args = payload.get("args") or []
        kwargs = payload.get("kwargs") or {}
        workdir = payload.get("workdir")
        capture = bool(payload.get("capture_stdout", True))
        if workdir:
            try:
                os.chdir(workdir)
            except Exception:
                pass
        # Ensure current working directory is importable
        if os.getcwd() not in sys.path:
            sys.path.insert(0, os.getcwd())
        if not module_name or not func_name:
            print(json.dumps({
                "ok": False,
                "error_type": "InvalidArgs",
                "error_message": "module and function are required",
                "stdout": "",
                "stderr": "",
                "result": None,
                "traceback": None,
            }))
            return
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        try:
            mod = importlib.import_module(module_name)
            func = getattr(mod, func_name)
            if not callable(func):
                raise TypeError(f"Object '{func_name}' is not callable")
            if capture:
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    result = func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            out = stdout_buf.getvalue()
            err = stderr_buf.getvalue()
            if not _json_safe(result):
                print(json.dumps({
                    "ok": False,
                    "error_type": "ResultNotSerializable",
                    "error_message": "Function result is not JSON serializable",
                    "stdout": out,
                    "stderr": err,
                    "result": None,
                    "traceback": None,
                }))
                return
            print(json.dumps({
                "ok": True,
                "result": result,
                "stdout": out,
                "stderr": err,
                "error_type": None,
                "error_message": None,
                "traceback": None,
            }))
        except Exception as e:  # noqa: BLE001
            out = stdout_buf.getvalue()
            err = stderr_buf.getvalue()
            print(json.dumps({
                "ok": False,
                "result": None,
                "stdout": out,
                "stderr": err,
                "error_type": e.__class__.__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc(),
            }))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({
            "ok": False,
            "result": None,
            "stdout": "",
            "stderr": "",
            "error_type": e.__class__.__name__,
            "error_message": str(e),
            "traceback": traceback.format_exc(),
        }))


if __name__ == "__main__":
    main()

