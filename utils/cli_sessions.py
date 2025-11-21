"""
Gestión de sesiones de CLI interactivas usando pexpect.
"""

from __future__ import annotations

import os
import re
import signal
import time
import uuid
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import pexpect

LOG_DIR = Path("data/cli_sessions")
DEPENDENCY_MARKERS = (
    "modulenotfounderror",
    "no module named",
    "importerror",
    "pkg_resources.distributionnotfound",
    "cannot import name",
    "command not found",
    "executable file not found",
    "file not found error",
    "no such file or directory",
    "contextualversionconflict",
)
NETWORK_MARKERS = (
    "connectionerror",
    "failed to establish a new connection",
    "max retries exceeded",
    "name or service not known",
    "temporary failure in name resolution",
    "getaddrinfo failed",
    "network is unreachable",
    "timed out",
    "remote disconnected",
    "httpsconnectionpool",
    "httpconnectionpool",
    "sslv3 alert handshake failure",
    "certificate verify failed",
    "connection refused",
    "tlsv1 alert",
    "proxyerror",
)
EOF_MARKERS = (
    "eoferror",
    "eof when reading a line",
    "end of file when reading input",
)


def _ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def _merge_env(custom_env: Optional[Dict[str, str]]) -> Dict[str, str]:
    merged = dict(os.environ)
    if custom_env:
        merged.update({k: str(v) for k, v in custom_env.items()})
    return merged


def _detect_prompt(text: str, prompt_pattern: Optional[str] = None) -> bool:
    """
    Heurística simple para marcar si la CLI está esperando entrada.
    """
    stripped = text.rstrip()
    if not stripped:
        return False
    if prompt_pattern:
        try:
            if re.search(prompt_pattern, stripped):
                return True
        except re.error:
            # Si el patrón no es válido, caemos a heurística.
            pass
    lines = stripped.splitlines()
    tail = lines[-1]
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
    common_prompts = (
        "enter option",
        "enter a choice",
        "choose an option",
        "selection",
        "input",
        "query",
        "prompt",
        "your choice",
    )
    if any(tail.lower().strip().startswith(prefix) for prefix in common_prompts):
        return True
    if any(tail.endswith(suffix) for suffix in prompt_suffixes):
        return True
    # Si la última línea está vacía pero la penúltima termina en prompt, considerar awaiting_input.
    if len(lines) >= 2 and not tail.strip():
        prev = lines[-2]
        if any(prev.endswith(suffix) for suffix in prompt_suffixes):
            return True
    return False


def _build_status_hint(alive: bool, awaiting_input: bool) -> Dict[str, str]:
    if not alive:
        return {
            "status_hint": "Sesión terminada.",
            "next_step": "Reinicia con cli_restart o lanza una nueva con cli_start.",
        }
    if awaiting_input:
        return {
            "status_hint": "Esperando tu entrada.",
            "next_step": "Envía la opción o comando con cli_send.",
        }
    return {
        "status_hint": "Proceso en curso, aún no pide entrada.",
        "next_step": "Llama de nuevo a cli_send (puede ser texto vacío) tras unos segundos para leer más salida.",
    }


def _enrich_hints(hints: Dict[str, str], output: str, conda_env: Optional[str]) -> Dict[str, str]:
    """
    Añade orientación contextual sobre fallos comunes (dependencias o red).
    """
    if not output:
        return hints

    normalized = output.lower()
    advice = []

    dependency_issue = any(marker in normalized for marker in DEPENDENCY_MARKERS)
    network_issue = any(marker in normalized for marker in NETWORK_MARKERS)
    eof_issue = any(marker in normalized for marker in EOF_MARKERS) or ("eof" in normalized and "input" in normalized)

    if dependency_issue:
        advice.append(
            "Si falta algún paquete, pregunta si debes usar otro entorno conda (parámetro conda_env) o instalarlo antes de relanzar."
        )
    if network_issue:
        advice.append(
            "Si el script necesita internet (LLM/APIs), consulta si puedes lanzarlo con permisos de red o cómo habilitar el acceso."
        )
    if eof_issue:
        advice.append(
            "Se detectó EOF al leer entrada; usa batch_queries para enviar preguntas en bloque o confirma que el comando tenga TTY disponible."
        )
    if conda_env and (dependency_issue or network_issue or eof_issue):
        advice.append(f"Usa conda_env='{conda_env}' si ese es el entorno esperado.")

    if advice:
        combined = " ".join(advice)
        hints["next_step"] = f"{hints.get('next_step', '').rstrip()} {combined}".strip()
    return hints


@dataclass
class CLISession:
    session_id: str
    command: str
    conda_env: Optional[str]
    workdir: Optional[str]
    env: Dict[str, str]
    process: pexpect.spawn
    logfile_path: Path
    log_enabled: bool
    batch_queries: Optional[list[str]] = None
    prompt_pattern: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def is_alive(self) -> bool:
        return self.process.isalive()

    def append_log(self, text: str) -> None:
        if not self.log_enabled:
            return
        try:
            with self.logfile_path.open("a", encoding="utf-8") as handle:
                handle.write(text)
        except Exception:
            # No interferir con el flujo si fallan los logs.
            pass


SESSIONS: Dict[str, CLISession] = {}


def _resolve_script_path(tokens: list[str], workdir: Optional[str]) -> list[str]:
    """
    Asegura que la ruta del script (si aplica) sea absoluta y exista.
    """
    if not tokens:
        return tokens

    script_index: Optional[int] = None
    if tokens[0].endswith(".py"):
        script_index = 0
    elif len(tokens) >= 2 and tokens[0].startswith("python"):
        script_index = 1

    if script_index is None:
        return tokens

    script_candidate = Path(tokens[script_index])
    candidates = [
        script_candidate,
        Path(workdir) / script_candidate if workdir else None,
        Path.cwd() / script_candidate,
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            tokens[script_index] = str(candidate.resolve())
            return tokens

    raise FileNotFoundError(
        f"No se encontró el script {script_candidate}. Ajusta workdir, usa ruta absoluta o corrige el comando."
    )


def _prepare_command(command: str, conda_env: Optional[str], workdir: Optional[str], batch_queries: Optional[list[str]]) -> Tuple[str, list[str]]:
    """
    Construye el comando final, resolviendo rutas y permitiendo modo batch por tubería.
    """
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ValueError("El comando contiene comillas o escapes inválidos.") from exc

    tokens = _resolve_script_path(tokens, workdir)
    base_cmd = shlex.join(tokens) if tokens else command
    if conda_env:
        base_cmd = f"conda run -n {conda_env} {base_cmd}"

    if batch_queries:
        escaped_queries = " ".join(shlex.quote(q) for q in batch_queries)
        piped = f"printf '%s\\n' {escaped_queries} | {base_cmd}"
        return "bash", ["-lc", piped]

    return "bash", ["-lc", base_cmd]


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
    if text and session.log_enabled:
        session.append_log(text)
        awaiting_input = _detect_prompt(text, prompt_pattern=session.prompt_pattern)
    elif session.is_alive():
        awaiting_input = True
    return text, awaiting_input


def start_session(
    command: str,
    conda_env: Optional[str] = None,
    workdir: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    batch_queries: Optional[list[str]] = None,
    prompt_pattern: Optional[str] = None,
    timeout: float = 1.5,
    max_bytes: int = 16000,
    log_enabled: bool = True,
) -> Dict[str, object]:
    """
    Inicia una sesión CLI interactiva y devuelve la salida inicial.
    """
    cleaned = (command or "").strip()
    if not cleaned:
        raise ValueError("Debes proporcionar un comando para iniciar la sesión.")
    if batch_queries is not None:
        if not isinstance(batch_queries, list) or not all(isinstance(item, str) for item in batch_queries):
            raise ValueError("batch_queries debe ser una lista de cadenas.")
    if prompt_pattern is not None and not isinstance(prompt_pattern, str):
        raise ValueError("prompt_pattern debe ser una cadena con una expresión regular.")
    exec_cmd, cmd_args = _prepare_command(cleaned, conda_env=conda_env, workdir=workdir, batch_queries=batch_queries)

    session_id = str(uuid.uuid4())
    log_path = Path("")
    if log_enabled:
        _ensure_log_dir()
        log_path = LOG_DIR / f"{session_id}.log"

    merged_env = _merge_env(env)
    try:
        proc = pexpect.spawn(
            exec_cmd,
            args=cmd_args,
            cwd=workdir or None,
            env=merged_env,
            encoding="utf-8",
            echo=False,
        )
    except (pexpect.exceptions.ExceptionPexpect, OSError) as exc:
        error_hint = (
            "No se pudo lanzar el comando. Verifica el comando, comprueba el entorno conda indicado o instala dependencias antes de reintentar."
        )
        raise RuntimeError(error_hint) from exc
    session = CLISession(
        session_id=session_id,
        command=cleaned,
        conda_env=conda_env,
        workdir=workdir,
        env=env or {},
        process=proc,
        logfile_path=log_path,
        log_enabled=log_enabled,
        batch_queries=batch_queries,
        prompt_pattern=prompt_pattern,
    )
    SESSIONS[session_id] = session
    output, awaiting_input = _drain_output(session, timeout=timeout, max_bytes=max_bytes)
    alive = session.is_alive()
    hints = _enrich_hints(
        _build_status_hint(alive=alive, awaiting_input=awaiting_input),
        output,
        conda_env=conda_env,
    )
    return {
        "session_id": session_id,
        "output": output,
        "awaiting_input": awaiting_input,
        "alive": alive,
        "log_path": str(log_path),
        "conda_env": conda_env or "",
        "prompt_pattern": prompt_pattern or "",
        **hints,
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
        hints = _enrich_hints(
            _build_status_hint(alive=False, awaiting_input=False),
            output,
            conda_env=session.conda_env,
        )
        return {
            "session_id": session_id,
            "output": output,
            "awaiting_input": False,
            "alive": False,
            "log_path": str(session.logfile_path),
            "conda_env": session.conda_env or "",
            "prompt_pattern": session.prompt_pattern or "",
            **hints,
        }
    session.process.sendline(text or "")
    output, awaiting_input = _drain_output(session, timeout=timeout, max_bytes=max_bytes)
    alive = session.is_alive()
    hints = _enrich_hints(
        _build_status_hint(alive=alive, awaiting_input=awaiting_input),
        output,
        conda_env=session.conda_env,
    )
    return {
        "session_id": session_id,
        "output": output,
        "awaiting_input": awaiting_input,
        "alive": alive,
        "log_path": str(session.logfile_path),
        "conda_env": session.conda_env or "",
        "prompt_pattern": session.prompt_pattern or "",
        **hints,
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
    hints = _enrich_hints(
        _build_status_hint(alive=False, awaiting_input=False),
        output,
        conda_env=session.conda_env,
    )
    return {
        "session_id": session_id,
        "output": output,
        "awaiting_input": False,
        "alive": session.is_alive(),
        "log_path": str(session.logfile_path),
        "conda_env": session.conda_env or "",
        "prompt_pattern": session.prompt_pattern or "",
        **hints,
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
        conda_env=session.conda_env,
        workdir=session.workdir,
        env=session.env,
        batch_queries=session.batch_queries,
        timeout=timeout,
        max_bytes=max_bytes,
    )


__all__ = [
    "start_session",
    "send_input",
    "stop_session",
    "restart_session",
]
