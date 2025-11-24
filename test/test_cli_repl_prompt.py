from __future__ import annotations

import os
import sys
import time
from pathlib import Path as _Path

import pytest

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.cli_sessions import start_session, send_lines, send_input


def _require_pty():
    try:
        m, s = os.openpty()
        os.close(m)
        os.close(s)
    except Exception:
        pytest.skip("PTY devices unavailable in this environment; skipping REPL test.")


def test_module_repl_shows_prompt_and_accepts_input():
    _require_pty()
    # Launch interactive REPL executing a simple print first
    cmd = "python -u -i -c 'print(\"ready\")'"
    res = start_session(command=cmd, timeout=0.2, max_bytes=4096, log_enabled=False)
    sid = res["session_id"]
    try:
        # Poll a bit until we see a prompt or 'ready' + prompt
        buf = res.get("output", "")
        deadline = time.time() + 3.0
        while time.time() < deadline and (">>>" not in buf):
            r = send_input(session_id=sid, text="", timeout=0.15, max_bytes=2048)
            buf += r.get("output", "")
            if ">>>" in buf:
                break
            time.sleep(0.05)
        assert ">>>" in buf
        # Send an expression and expect its result and prompt
        r2 = send_lines(session_id=sid, lines=["1+1"], timeout=0.2, max_bytes=2048)
        out2 = r2.get("output", "")
        assert "2" in out2
        # We might or might not see the prompt in the same chunk; poll once more
        r3 = send_input(session_id=sid, text="", timeout=0.15, max_bytes=2048)
        out3 = r3.get("output", "")
        assert ">>>" in (out2 + out3)
    finally:
        # Hard stop to ensure cleanup
        from utils.cli_sessions import stop_session
        stop_session(sid, kill=True, drop=True)

