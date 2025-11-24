from __future__ import annotations

import os
import sys
from pathlib import Path as _Path

import pytest

# Ensure repository root in sys.path for local imports
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.cli_sessions import start_session


def _require_pty():
    try:
        m, s = os.openpty()
        os.close(m)
        os.close(s)
    except Exception:
        pytest.skip("PTY devices unavailable in this environment; skipping stdin preinject test.")


def test_cli_start_with_stdin_lines_handles_input_prompt():
    _require_pty()
    # Script prompts for name and greets
    cmd = "python -u scripts/cli_cases/greet_prompt.py"
    res = start_session(command=cmd, timeout=0.3, max_bytes=4096, log_enabled=False, stdin_lines=["Alice"])
    out = res.get("output", "")
    # Should contain the prompt and the greeting
    assert isinstance(out, str)
    assert "Enter your name:" in out
    assert "Hello, Alice!" in out
    # Process should be finished (no awaiting_input)
    assert res.get("alive") is False
    assert res.get("awaiting_input") is False
    # Provide termination details
    assert res.get("termination_reason") in {"Exited", "EOF_on_stdin", "Signaled", "UnknownError", None}
