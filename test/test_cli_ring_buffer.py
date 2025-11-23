from __future__ import annotations

import sys
from pathlib import Path as _Path
import time

import pytest

# Ensure repository root in sys.path for local imports
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.cli_sessions import start_session, send_input, stop_session


def _require_pty():
    """Skip tests if the environment has no PTY devices available."""
    import os
    try:
        m, s = os.openpty()
        os.close(m)
        os.close(s)
    except Exception:
        pytest.skip("PTY devices unavailable in this environment; skipping CLI ring buffer tests.")


def _streaming_cmd(lines: int = 200, sleep_ms: int = 2) -> str:
    # Comando Python que emite varias líneas con pequeños delays y luego duerme
    delay = max(0, sleep_ms) / 1000.0
    return (
        "python -u -c \"import sys,time; "
        f"[sys.stdout.write(f'line {{i}}\\n') or sys.stdout.flush() or time.sleep({delay}) for i in range({lines})]; "
        "time.sleep(0.05)\""
    )


def test_cli_ring_buffer_and_deltas():
    _require_pty()
    cmd = _streaming_cmd(lines=100, sleep_ms=2)
    res = start_session(command=cmd, timeout=0.1, max_bytes=4096, log_enabled=False)
    sid = res["session_id"]
    try:
        first = res.get("output", "")
        # Debe llegar algo (al menos unas pocas líneas)
        assert isinstance(first, str)
        # Recoger más delta tras un pequeño tiempo
        res2 = send_input(session_id=sid, text="", timeout=0.2, max_bytes=100_000)
        out2 = res2.get("output", "")
        assert isinstance(out2, str)
        # En total debemos tener múltiples apariciones de "line "
        total_count = (first + out2).count("line ")
        assert total_count >= 10
        # Un nuevo pull inmediato suele devolver poco o nada si no hubo nuevo output
        res3 = send_input(session_id=sid, text="", timeout=0.05, max_bytes=100_000)
        out3 = res3.get("output", "")
        assert isinstance(out3, str)
    finally:
        stop_session(sid, kill=True, drop=True)


def test_cli_send_respects_max_bytes_limit():
    _require_pty()
    cmd = _streaming_cmd(lines=50, sleep_ms=1)
    res = start_session(command=cmd, timeout=0.05, max_bytes=128, log_enabled=False)
    sid = res["session_id"]
    try:
        # Forzar un límite bajo en la lectura
        res2 = send_input(session_id=sid, text="", timeout=0.1, max_bytes=64)
        out = res2.get("output", "")
        # Debe ser string y como máximo 64 bytes aprox (puede pasarse por UTF-8),
        # toleramos +-16 bytes por codificación de salto de línea y variaciones
        assert isinstance(out, str)
        assert len(out.encode("utf-8", errors="ignore")) <= 96
    finally:
        stop_session(sid, kill=True, drop=True)
