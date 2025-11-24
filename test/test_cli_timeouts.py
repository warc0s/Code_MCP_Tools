from __future__ import annotations

import os
import sys
import time
from pathlib import Path as _Path

import pytest

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.cli_sessions import start_session, send_input, SESSIONS


def _require_pty():
    try:
        m, s = os.openpty()
        os.close(m)
        os.close(s)
    except Exception:
        pytest.skip("PTY devices unavailable in this environment; skipping timeout test.")


def test_timeout_enforced_on_idle_and_lifetime():
    _require_pty()
    # Start a simple Python that sleeps briefly
    cmd = "python -u -c 'import time; time.sleep(0.2); print(\"done\")'"
    res = start_session(command=cmd, timeout=0.05, max_bytes=2048, log_enabled=False)
    sid = res["session_id"]
    try:
        # Force timeouts by manipulating session timestamps (white-box for deterministic test)
        sess = SESSIONS[sid]
        now = time.time()
        sess.created_at = now - 4000  # beyond lifetime
        sess.last_send_ts = now - 4000  # beyond idle
        r = send_input(session_id=sid, text="", timeout=0.1, max_bytes=2048)
        assert r.get("alive") is False
        assert r.get("termination_reason") == "Timeout"
    finally:
        # Ensure cleanup
        from utils.cli_sessions import stop_session
        try:
            stop_session(sid, kill=True, drop=True)
        except Exception:
            pass

