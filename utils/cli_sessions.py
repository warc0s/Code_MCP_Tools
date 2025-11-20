"""
Gestión de sesiones de CLI interactivas usando pexpect.
"""

from __future__ import annotations

import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import pexpect

LOG_DIR = Path("data/cli_sessions")


def _ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def _merge_env(custom_env: Optional[Dict[str, str]]) -> Dict[str, str]:
    merged = dict(os.environ)
    if custom_env:
        merged.update({k: str(v) for k, v in custom_env.items()})
    return merged


def _detect_prompt(text: str) -> bool:
    """
    Heurística simple para marcar si la CLI está esperando entrada.
    """
    stripped = text.rstrip()
    if not stripped:
        return False
    tail = stripped.splitlines()[-1]
    prompt_suffixes = (
        ">",
        ":",
        "?",
        "> ",
        ": ",
        "? ",
        ")",
        ") ",
    )
    return any(tail.endswith(suffix) for suffix in prompt_suffixes)


@dataclass
class CLISession:
    session_id: str
    command: str
    workdir: Optional[str]
    env: Dict[str, str]
    process: pexpect.spawn
    logfile_path: Path
    created_at: float = field(default_factory=time.time)

    def is_alive(self) -> bool:
        return self.process.isalive()

    def append_log(self, text: str) -> None:
        try:
            with self.logfile_path.open("a", encoding="utf-8") as handle:
                handle.write(text)
        except Exception:
            # No interferir con el flujo si fallan los logs.
            pass


SESSIONS: Dict[str, CLISession] = {}


def _drain_output(session: CLISession, timeout: float = 1.5, max_bytes: int = 16000) -> Tuple[str, bool]:
    """
    Lee la salida disponible sin bloquear más allá del timeout.
    Devuelve el texto acumulado y si se detecta prompt.
    """
    output_chunks = []
    end_time = time.time() + max(timeout, 0.1)
    bytes_read = 0
    awaiting_input = False

    while time.time() < end_time and bytes_read < max_bytes:
        remaining = end_time - time.time()
        try:
            chunk = session.process.read_nonblocking(size=1024, timeout=max(remaining, 0.1))
            if not chunk:
                continue
            output_chunks.append(chunk)
            bytes_read += len(chunk.encode("utf-8", errors="ignore"))
        except pexpect.TIMEOUT:
            break
        except pexpect.EOF:
            break
        except Exception:
            break

    text = "".join(output_chunks)
    if text:
        session.append_log(text)
        awaiting_input = _detect_prompt(text)
    elif session.is_alive():
        awaiting_input = True
    return text, awaiting_input


def start_session(
    command: str,
    workdir: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: float = 1.5,
    max_bytes: int = 16000,
) -> Dict[str, object]:
    """
    Inicia una sesión CLI interactiva y devuelve la salida inicial.
    """
    cleaned = (command or "").strip()
    if not cleaned:
        raise ValueError("Debes proporcionar un comando para iniciar la sesión.")

    session_id = str(uuid.uuid4())
    _ensure_log_dir()
    log_path = LOG_DIR / f"{session_id}.log"

    merged_env = _merge_env(env)
    proc = pexpect.spawn(
        cleaned,
        cwd=workdir or None,
        env=merged_env,
        encoding="utf-8",
        echo=False,
    )
    session = CLISession(
        session_id=session_id,
        command=cleaned,
        workdir=workdir,
        env=env or {},
        process=proc,
        logfile_path=log_path,
    )
    SESSIONS[session_id] = session
    output, awaiting_input = _drain_output(session, timeout=timeout, max_bytes=max_bytes)
    return {
        "session_id": session_id,
        "output": output,
        "awaiting_input": awaiting_input,
        "alive": session.is_alive(),
        "log_path": str(log_path),
    }


def send_input(
    session_id: str,
    text: str,
    timeout: float = 1.5,
    max_bytes: int = 16000,
) -> Dict[str, object]:
    session = SESSIONS.get(session_id)
    if not session:
        raise ValueError("Sesión no encontrada. Inicia una sesión antes de enviar entrada.")
    if not session.is_alive():
        output, _ = _drain_output(session, timeout=timeout, max_bytes=max_bytes)
        return {
            "session_id": session_id,
            "output": output,
            "awaiting_input": False,
            "alive": False,
            "log_path": str(session.logfile_path),
        }
    session.process.sendline(text or "")
    output, awaiting_input = _drain_output(session, timeout=timeout, max_bytes=max_bytes)
    return {
        "session_id": session_id,
        "output": output,
        "awaiting_input": awaiting_input,
        "alive": session.is_alive(),
        "log_path": str(session.logfile_path),
    }


def stop_session(session_id: str, kill: bool = False) -> Dict[str, object]:
    session = SESSIONS.get(session_id)
    if not session:
        raise ValueError("Sesión no encontrada.")
    if session.is_alive():
        try:
            if kill:
                session.process.kill(signal.SIGKILL)
            else:
                session.process.kill(signal.SIGINT)
        except Exception:
            pass
    # Intentar drenar salida final
    output, _ = _drain_output(session, timeout=0.5, max_bytes=8000)
    return {
        "session_id": session_id,
        "output": output,
        "awaiting_input": False,
        "alive": session.is_alive(),
        "log_path": str(session.logfile_path),
    }


def restart_session(
    session_id: str,
    timeout: float = 1.5,
    max_bytes: int = 16000,
) -> Dict[str, object]:
    session = SESSIONS.get(session_id)
    if not session:
        raise ValueError("Sesión no encontrada.")
    stop_session(session_id, kill=False)
    return start_session(
        command=session.command,
        workdir=session.workdir,
        env=session.env,
        timeout=timeout,
        max_bytes=max_bytes,
    )


__all__ = [
    "start_session",
    "send_input",
    "stop_session",
    "restart_session",
]
