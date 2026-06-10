"""
Gestión de sesiones de CLI interactivas usando pexpect (backend único pexpect-only).

Endurecimientos clave:
- Drainer en background por sesión que lee del PTY de forma continua y acumula en
  un ring buffer en memoria, limitado por bytes (best-effort, sin bloquear).
- `last_activity` real por sesión y limpieza periódica.
- Señales más robustas: interrupción suave (Ctrl+C) y parada con señales al grupo
  de procesos; tolera EOF y EIO en macOS.
- Tamaño de TTY configurable por defecto (reduce wraps raros en CLIs).

Notas:
- La API pública (start_session, send_input, stop_session, restart_session) se
  mantiene estable. Se añade soporte de `max_bytes` para limitar la lectura por
  llamada (delta desde el último pull) y se mejora la detección de prompt
  desacoplándola de los logs.
"""

from __future__ import annotations

import os
import re
import signal
import time
import uuid
import shlex
import subprocess
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path
from typing import Dict, Optional, Tuple

import pexpect
import errno
import threading
import re as _re

LOG_DIR = Path("data/cli_sessions")
# Tamaños y límites por defecto
DEFAULT_RING_MAX_BYTES = int(os.getenv("CLI_RING_BUFFER_MAX_BYTES", str(512 * 1024)))  # 512 KiB
DEFAULT_RING_MAX_BYTES_HIGH = int(os.getenv("CLI_RING_BUFFER_MAX_BYTES_HIGH", str(2 * 1024 * 1024)))  # 2 MiB
READ_CHUNK_BYTES = int(os.getenv("CLI_READ_CHUNK_BYTES", str(32 * 1024)))  # 32 KiB por lectura
DEFAULT_INACTIVITY_TTL = int(os.getenv("CLI_INACTIVITY_TTL_SEC", str(30 * 60)))  # 30 minutos (GC de sesiones inactivas)
# Timeouts de sesión (aplican a cualquier modo; recomendados para REPL)
DEFAULT_SESSION_LIFETIME_SEC = int(os.getenv("CLI_SESSION_LIFETIME_SEC", str(30 * 60)))  # 30 min vida total
DEFAULT_IDLE_TIMEOUT_SEC = int(os.getenv("CLI_IDLE_TIMEOUT_SEC", str(15 * 60)))  # 15 min sin interacción
MAX_SESSIONS = int(os.getenv("CLI_MAX_SESSIONS", "8"))
DEFAULT_TTY_ROWS = int(os.getenv("CLI_TTY_ROWS", "40"))
DEFAULT_TTY_COLS = int(os.getenv("CLI_TTY_COLS", "120"))
DEFAULT_CLEANUP_GRACE_SEC = float(os.getenv("CLI_CLEANUP_GRACE_SEC", "2.0"))
PYTHON_EXEC_MAP: Dict[str, str] = {}
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


def set_python_exec_map(mapping: Dict[str, str]) -> None:
    """Configure a mapping from conda_env name to absolute python executable path.

    Values must be non-empty strings; invalid entries are ignored. This overrides
    auto-discovery via `conda run` when present.
    """
    global PYTHON_EXEC_MAP
    clean: Dict[str, str] = {}
    for k, v in (mapping or {}).items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        key = k.strip()
        val = v.strip()
        if not key or not val:
            continue
        clean[key] = val
    PYTHON_EXEC_MAP = clean


_CONDA_ENV_PATTERN = _re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_conda_env(name: Optional[str]) -> Optional[str]:
    """Validate a conda environment name defensively.

    Accepts only letters, digits, underscores and hyphens (1..64 chars). Returns
    the original name if valid, or None if empty. Raises ValueError with user-
    friendly guidance when invalid (to avoid shell injection or misfires).
    """
    if name is None:
        return None
    trimmed = str(name).strip()
    if not trimmed:
        return None
    if not _CONDA_ENV_PATTERN.fullmatch(trimmed):
        raise ValueError(
            "Invalid conda_env. Use only letters, digits, '_' or '-' (1..64 chars). "
            "No spaces or shell symbols. For example: 'mcp', 'code_tools', 'env-01'."
        )
    return trimmed


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
            "next_step": "Restart with python_cli_restart or start a new one with python_cli_start.",
        }
    if awaiting_input:
        return {
            "status_hint": "Esperando tu entrada.",
            "next_step": "Send input with python_cli_send.",
        }
    return {
        "status_hint": "Proceso en curso, aún no pide entrada.",
        "next_step": "Call python_cli_send again (empty text allowed) after a few seconds to read more output.",
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
            "Se detectó EOF al leer entrada; usa stdin_lines para enviar entradas iniciales o confirma que el comando tenga TTY disponible."
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
    # Ring buffer (pendiente de enviar al cliente) y sincronización
    pending_chunks: deque[str] = field(default_factory=deque)
    pending_bytes: int = 0
    max_buffer_bytes: int = DEFAULT_RING_MAX_BYTES
    last_activity: float = field(default_factory=time.time)
    rows: int = DEFAULT_TTY_ROWS
    cols: int = DEFAULT_TTY_COLS
    reader_thread: Optional[threading.Thread] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Campos auxiliares
    last_output_ts: float = 0.0
    last_send_ts: float = 0.0
    ring_truncated: bool = False
    is_repl: bool = False
    eio_error: bool = False
    ring_discarded_bytes: int = 0
    killed_by_timeout: bool = False
    process_group_created: bool = False

    def is_alive(self) -> bool:
        try:
            return self.process.isalive()
        except (pexpect.ExceptionPexpect, OSError):
            return False

    def append_log(self, text: str) -> None:
        if not self.log_enabled:
            return
        try:
            with self.logfile_path.open("a", encoding="utf-8") as handle:
                handle.write(text)
        except Exception:
            # No interferir con el flujo si fallan los logs.
            pass

    def append_output(self, text: str) -> None:
        if not text:
            return
        with self.lock:
            self.pending_chunks.append(text)
            self.pending_bytes += len(text.encode("utf-8", errors="ignore"))
            # Recorta por tamaño máximo, descartando lo más antiguo
            while self.pending_bytes > self.max_buffer_bytes and self.pending_chunks:
                old = self.pending_chunks.popleft()
                dropped = len(old.encode("utf-8", errors="ignore"))
                self.pending_bytes -= dropped
                self.ring_discarded_bytes += dropped
            self.last_activity = time.time()
            self.last_output_ts = self.last_activity
            if self.pending_bytes >= self.max_buffer_bytes:
                self.ring_truncated = True

    def pull_output(self, max_bytes: int) -> str:
        """Devuelve y limpia hasta max_bytes de la cola pendiente.

        Si hay más de max_bytes pendientes, se devuelven los primeros max_bytes y
        se conserva el excedente para lecturas futuras.
        """
        with self.lock:
            if self.pending_bytes <= 0 or not self.pending_chunks:
                return ""
            out_parts: list[str] = []
            budget = max(1, int(max_bytes))
            # Consumir trozos mientras haya presupuesto
            while self.pending_chunks and budget > 0:
                chunk = self.pending_chunks[0]
                chunk_bytes = len(chunk.encode("utf-8", errors="ignore"))
                if chunk_bytes <= budget:
                    out_parts.append(chunk)
                    self.pending_chunks.popleft()
                    self.pending_bytes -= chunk_bytes
                    budget -= chunk_bytes
                else:
                    # Tomar una porción del chunk y dejar el resto en cabeza
                    # Convertimos a bytes para cortar exacto por bytes y decodificamos tolerante
                    raw = chunk.encode("utf-8", errors="ignore")
                    part = raw[:budget]
                    rest = raw[budget:]
                    out_parts.append(part.decode("utf-8", errors="ignore"))
                    self.pending_chunks[0] = rest.decode("utf-8", errors="ignore")
                    self.pending_bytes -= len(part)
                    budget = 0
            return "".join(out_parts)

    def mark_activity(self) -> None:
        self.last_activity = time.time()


SESSIONS: Dict[str, CLISession] = {}


def _start_reader_thread(session: CLISession) -> None:
    """
    Inicia un hilo lector que drena el PTY de la sesión y vuelca en el ring buffer.
    Maneja EOF y EIO (común en ptys al cerrar) como fin normal.
    """
    def _reader() -> None:
        try:
            # Ajuste de tamaño del TTY para reducir wraps raros
            try:
                session.process.setwinsize(session.rows, session.cols)
            except Exception:
                pass
            while not session.stop_event.is_set():
                # Si el proceso ya no está vivo, intentamos una última lectura y salimos
                if not session.is_alive():
                    try:
                        chunk = session.process.read_nonblocking(size=READ_CHUNK_BYTES, timeout=0.2)
                        if chunk:
                            session.append_output(chunk)
                            if session.log_enabled:
                                session.append_log(chunk)
                    except (pexpect.EOF, pexpect.TIMEOUT):
                        pass
                    except OSError as exc:
                        if getattr(exc, "errno", None) == errno.EIO:
                            # Tratar EIO como EOF del PTY
                            pass
                    break
                try:
                    chunk = session.process.read_nonblocking(size=READ_CHUNK_BYTES, timeout=0.4)
                    if chunk:
                        session.append_output(chunk)
                        if session.log_enabled:
                            session.append_log(chunk)
                    else:
                        # Nada leído, pequeño respiro
                        time.sleep(0.05)
                except pexpect.TIMEOUT:
                    # Sin datos este ciclo
                    continue
                except pexpect.EOF:
                    break
                except OSError as exc:
                    if getattr(exc, "errno", None) == errno.EIO:
                        session.eio_error = True
                        break
                    # Otros errores: evitar bloquear el hilo
                    break
        finally:
            session.stop_event.set()

    t = threading.Thread(target=_reader, name=f"cli-reader-{session.session_id}", daemon=True)
    session.reader_thread = t
    t.start()


def _is_under_root(candidate: Path, root: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False


def _resolve_workdir(workdir: Optional[str]) -> Optional[str]:
    if not workdir:
        return None
    repo_root = Path.cwd().resolve()
    candidate = Path(workdir)
    resolved = candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()
    if not _is_under_root(resolved, repo_root):
        raise ValueError("workdir outside repository.")
    return str(resolved)


def _resolve_script_path(tokens: list[str], workdir: Optional[str]) -> list[str]:
    """
    Asegura que la ruta del script (si aplica) sea absoluta y exista.
    """
    if not tokens:
        return tokens

    script_index: Optional[int] = None
    # Caso directo: se invoca el intérprete con un script .py directamente
    if tokens[0].endswith(".py"):
        script_index = 0
    # Caso 'python ... <script>.py ...' → localizar el primer token .py
    elif tokens[0].startswith("python"):
        for i in range(1, len(tokens)):
            tok = tokens[i]
            # Evitar flags como -c/-m/-u etc.
            if tok.startswith("-"):
                continue
            if tok.endswith(".py"):
                script_index = i
                break

    if script_index is None:
        return tokens

    script_candidate = Path(tokens[script_index])
    candidates = [
        script_candidate,
        Path(workdir) / script_candidate if workdir else None,
        Path.cwd() / script_candidate,
    ]
    repo_root = Path.cwd().resolve()
    for candidate in candidates:
        if candidate and candidate.is_file():
            resolved = candidate.resolve()
            if not _is_under_root(resolved, repo_root):
                raise ValueError("Script outside repository.")
            tokens[script_index] = str(resolved)
            return tokens

    raise FileNotFoundError(
        f"No se encontró el script {script_candidate}. Ajusta workdir, usa ruta absoluta o corrige el comando."
    )


def _is_repl_command(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except Exception:
        return False
    return any(tok == "-i" for tok in tokens)


def _resolve_python_executable(conda_env: Optional[str]) -> str:
    if not conda_env:
        return "python"
    mapped = PYTHON_EXEC_MAP.get(conda_env)
    if mapped:
        return mapped
    try:
        out = subprocess.run(
            ["conda", "run", "-n", conda_env, "python", "-c", "import sys; print(sys.executable)"]
            , check=True, capture_output=True, text=True
        )
        path = (out.stdout or "").strip().splitlines()[0].strip()
        return path or "python"
    except Exception:
        # Fallback marker to use conda wrapper as executable
        return f"conda:run:-n:{conda_env}"


def _prepare_command(command: str, conda_env: Optional[str], workdir: Optional[str], batch_queries: Optional[list[str]]) -> Tuple[str, list[str]]:
    """
    Construye (executable, argv) para spawn sin shell.
    """
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ValueError("El comando contiene comillas o escapes inválidos.") from exc
    tokens = _resolve_script_path(tokens, workdir)
    if not tokens:
        raise ValueError("Comando vacío tras parseo.")
    first = tokens[0]
    pyexec = _resolve_python_executable(conda_env)
    if pyexec.startswith("conda:run:-n:"):
        envname = pyexec.split(":")[-1]
        return "conda", ["run", "-n", envname] + tokens
    # Replace python front if present
    if first in {"python", "python3"} or first.endswith("python") or first.endswith("python3"):
        return pyexec, tokens[1:]
    if first.endswith(".py"):
        return pyexec, tokens
    # Otherwise return as-is (should still be Python-only by policy)
    return first, tokens[1:]


def _cleanup_sessions(max_age_seconds: int = DEFAULT_INACTIVITY_TTL) -> None:
    """
    Cierra procesos muertos o muy antiguos para evitar fugas y cuelgues.
    """
    now = time.time()
    for session_id, session in list(SESSIONS.items()):
        # Usar last_activity para GC más justo
        expired = (now - session.last_activity) > max_age_seconds
        alive = False
        try:
            alive = session.is_alive()
        except Exception:
            alive = False

        # Gracia: no borrar por 'not alive' si la sesión es muy reciente
        if not expired and not alive:
            age = now - getattr(session, "created_at", now)
            if age < DEFAULT_CLEANUP_GRACE_SEC:
                continue

        if expired or not alive:
            try:
                session.stop_event.set()
                if session.reader_thread and session.reader_thread.is_alive():
                    session.reader_thread.join(timeout=0.5)
                session.process.close(force=True)
            except Exception:
                pass
            SESSIONS.pop(session_id, None)


def _timeout_kill(session: CLISession, grace_sec: float = 2.0) -> None:
    if not session.is_alive():
        return
    session.killed_by_timeout = True
    try:
        # Señal suave al grupo si es posible
        try:
            pgid = os.getpgid(session.process.pid)
        except Exception:
            pgid = None
        if pgid and session.process_group_created:
            os.killpg(pgid, signal.SIGTERM)
        else:
            try:
                session.process.kill(signal.SIGTERM)
            except Exception:
                pass
        deadline = time.time() + max(0.0, grace_sec)
        while time.time() < deadline and session.is_alive():
            time.sleep(0.05)
        if session.is_alive():
            if pgid and session.process_group_created:
                os.killpg(pgid, signal.SIGKILL)
            else:
                try:
                    session.process.kill(signal.SIGKILL)
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        session.stop_event.set()


def _drain_output_pull(
    session: CLISession,
    timeout: float,
    max_bytes: int,
    stop_on_first_data: bool = True,
) -> Tuple[str, bool]:
    """
    Espera hasta `timeout` para acumular salida nueva en el ring buffer y devuelve
    hasta `max_bytes` del delta pendiente. Marca awaiting_input por heurística.
    """
    deadline = time.time() + max(0.0, float(timeout))
    # Espera activa breve: sal si ya hay datos o al expirar
    while time.time() < deadline:
        with session.lock:
            have_data = session.pending_bytes > 0
        if have_data and stop_on_first_data:
            break
        # Si el proceso ya terminó y no hay datos, salir
        if not session.is_alive():
            break
        time.sleep(0.05)
    text = session.pull_output(max_bytes=max_bytes)
    awaiting_input = False
    # awaiting_input solo confiable en REPL (prompt >>> o ...)
    if text and session.is_repl:
        try:
            PROMPT_RE = _re.compile(r"(?m)^(>>> |\.\.\. )")
            lines = text.splitlines()[-10:]
            for line in reversed(lines):
                if PROMPT_RE.match(line):
                    awaiting_input = True
                    break
        except Exception:
            awaiting_input = False
    return text, awaiting_input


def _map_signal(sig: Optional[int]) -> Optional[str]:
    if sig is None:
        return None
    try:
        return signal.Signals(sig).name
    except Exception:
        return f"SIG{int(sig)}"


def _looks_like_eof_on_stdin(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return ("eoferror" in t and "reading a line" in t) or ("eof" in t and "stdin" in t)


def _derive_termination(session: CLISession, tail_text: str) -> Tuple[str, Optional[int], Optional[str]]:
    try:
        alive = session.is_alive()
    except Exception:
        alive = False
    if alive:
        return "Running", None, None
    exit_code = getattr(session.process, "exitstatus", None)
    sig = _map_signal(getattr(session.process, "signalstatus", None))
    if _looks_like_eof_on_stdin(tail_text):
        return "EOF_on_stdin", exit_code, sig
    if session.killed_by_timeout:
        return "Timeout", exit_code, sig
    if sig is not None:
        return "Signaled", exit_code, sig
    if exit_code is not None:
        return "Exited", exit_code, sig
    return "UnknownError", exit_code, sig


def start_session(
    command: str,
    conda_env: Optional[str] = None,
    workdir: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    batch_queries: Optional[list[str]] = None,
    stdin_lines: Optional[list[str]] = None,
    prompt_pattern: Optional[str] = None,
    timeout: float = 1.5,
    max_bytes: int = 16000,
    log_enabled: bool = True,
    ring_max_bytes: Optional[int] = None,
) -> Dict[str, object]:
    """
    Inicia una sesión CLI interactiva y devuelve la salida inicial.
    """
    _cleanup_sessions()
    if len(SESSIONS) >= MAX_SESSIONS:
        raise RuntimeError("Número máximo de sesiones alcanzado. Cierra alguna antes de abrir otra.")
    cleaned = (command or "").strip()
    if not cleaned:
        raise ValueError("Debes proporcionar un comando para iniciar la sesión.")
    if batch_queries is not None:
        if not isinstance(batch_queries, list) or not all(isinstance(item, str) for item in batch_queries):
            raise ValueError("batch_queries debe ser una lista de cadenas.")
    if stdin_lines is not None:
        if not isinstance(stdin_lines, list) or not all(isinstance(item, str) for item in stdin_lines):
            raise ValueError("stdin_lines debe ser una lista de cadenas.")
    if prompt_pattern is not None and not isinstance(prompt_pattern, str):
        raise ValueError("prompt_pattern debe ser una cadena con una expresión regular.")
    # Validate conda env defensively (prevents shell injection and common mistakes)
    try:
        conda_env = _validate_conda_env(conda_env)
    except ValueError as exc:
        # Provide actionable advice consistent with other hints
        raise ValueError(
            f"{exc} If you do not need a conda env, omit the field. If you do, create it first and try again."
        ) from exc

    # Siempre spawn directo para permitir stdin_lines sin shell
    resolved_workdir = _resolve_workdir(workdir)
    exec_cmd, cmd_args = _prepare_command(
        cleaned, conda_env=conda_env, workdir=resolved_workdir, batch_queries=None
    )

    session_id = str(uuid.uuid4())
    log_path = Path("")
    if log_enabled:
        _ensure_log_dir()
        log_path = LOG_DIR / f"{session_id}.log"

    merged_env = _merge_env(env)
    try:
        def _spawn(preexec_fn):
            return pexpect.spawn(
                exec_cmd,
                args=cmd_args,
                cwd=resolved_workdir,
                env=merged_env,
                encoding="utf-8",
                echo=False,
                preexec_fn=preexec_fn,
            )

        # Crear nuevo grupo de procesos (POSIX) para señales al grupo
        preexec = None
        try:
            preexec = os.setsid
        except Exception:
            preexec = None
        process_group_created = preexec is not None
        try:
            proc = _spawn(preexec)
        except PermissionError as exc:
            exc_text = str(exc).lower()
            is_eperm = (
                exc.errno == errno.EPERM
                or "[errno 1]" in exc_text
                or "operation not permitted" in exc_text
            )
            if preexec is None or not is_eperm:
                raise
            # Some constrained runners deny setsid in the child process; retry without a process group.
            proc = _spawn(None)
            process_group_created = False
    except (pexpect.exceptions.ExceptionPexpect, OSError) as exc:
        error_hint = (
            "No se pudo lanzar el comando. Verifica el comando, revisa el entorno conda (usa solo letras/dígitos/_/-) "
            "o instala dependencias antes de reintentar."
        )
        raise RuntimeError(error_hint) from exc
    session = CLISession(
        session_id=session_id,
        command=cleaned,
        conda_env=conda_env,
        workdir=resolved_workdir,
        env=merged_env,
        process=proc,
        logfile_path=log_path,
        log_enabled=log_enabled,
        batch_queries=batch_queries,
        prompt_pattern=prompt_pattern,
        is_repl=_is_repl_command(cleaned),
        process_group_created=process_group_created,
    )
    if ring_max_bytes and isinstance(ring_max_bytes, int) and ring_max_bytes > 0:
        session.max_buffer_bytes = int(ring_max_bytes)
    SESSIONS[session_id] = session
    # Ajustar TTY y arrancar drainer
    _start_reader_thread(session)
    # Preinyectar líneas en stdin si procede
    if stdin_lines:
        for line in stdin_lines:
            try:
                session.process.sendline(line)
                session.last_send_ts = time.time()
                session.mark_activity()
            except Exception:
                break
    # Esperar un poco y devolver delta acumulado
    output, awaiting_input = _drain_output_pull(
        session,
        timeout=timeout,
        max_bytes=max_bytes,
        stop_on_first_data=not bool(stdin_lines),
    )
    alive = session.is_alive()
    if not alive:
        awaiting_input = False
    term_reason, exit_code, sig = _derive_termination(session, output)
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
        "termination_reason": term_reason,
        "exit_code": exit_code,
        "signal": sig,
        "ring_buffer_bytes": session.max_buffer_bytes,
        "ring_buffer_truncated": session.ring_truncated,
        "ring_buffer_discarded_bytes": session.ring_discarded_bytes,
        **hints,
    }


def send_input(
    session_id: str,
    text: str,
    timeout: float = 1.5,
    max_bytes: int = 16000,
) -> Dict[str, object]:
    # Buscar primero sin limpiar para evitar borrar una sesión recién creada por error
    session = SESSIONS.get(session_id)
    if not session:
        # Hacer una limpieza y reintentar localizar la sesión (un solo intento)
        _cleanup_sessions()
        session = SESSIONS.get(session_id)
    if not session:
        raise ValueError("Sesión no encontrada. Inicia una sesión antes de enviar entrada.")
    # Enforce lifetime/idle timeouts before interacting
    now = time.time()
    idle_anchor = session.last_send_ts or session.created_at
    expired = (
        (now - session.created_at) > DEFAULT_SESSION_LIFETIME_SEC
        or (now - idle_anchor) > DEFAULT_IDLE_TIMEOUT_SEC
    )
    if expired:
        session.killed_by_timeout = True
        if session.is_alive():
            _timeout_kill(session)
    if not session.is_alive():
        output, _ = _drain_output_pull(session, timeout=timeout, max_bytes=max_bytes)
        term_reason, exit_code, sig = _derive_termination(session, output)
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
            "termination_reason": term_reason,
            "exit_code": exit_code,
            "signal": sig,
            "ring_buffer_bytes": session.max_buffer_bytes,
            "ring_buffer_truncated": session.ring_truncated,
            **hints,
        }
    session.process.sendline(text or "")
    session.mark_activity()
    session.last_send_ts = time.time()
    output, awaiting_input = _drain_output_pull(session, timeout=timeout, max_bytes=max_bytes)
    alive = session.is_alive()
    if not alive:
        awaiting_input = False
    term_reason, exit_code, sig = _derive_termination(session, output)
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
        "termination_reason": term_reason,
        "exit_code": exit_code,
        "signal": sig,
        "ring_buffer_bytes": session.max_buffer_bytes,
        "ring_buffer_truncated": session.ring_truncated,
        "ring_buffer_discarded_bytes": session.ring_discarded_bytes,
        **hints,
    }


def send_lines(
    session_id: str,
    lines: list[str],
    timeout: float = 1.5,
    max_bytes: int = 16000,
) -> Dict[str, object]:
    session = SESSIONS.get(session_id)
    if not session:
        _cleanup_sessions()
        session = SESSIONS.get(session_id)
    if not session:
        raise ValueError("Sesión no encontrada. Inicia una sesión antes de enviar entrada.")
    if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
        raise ValueError("stdin_lines debe ser una lista de cadenas.")
    # Enforce timeouts first
    now = time.time()
    idle_anchor = session.last_send_ts or session.created_at
    expired = (
        (now - session.created_at) > DEFAULT_SESSION_LIFETIME_SEC
        or (now - idle_anchor) > DEFAULT_IDLE_TIMEOUT_SEC
    )
    if expired:
        session.killed_by_timeout = True
        if session.is_alive():
            _timeout_kill(session)
    if not session.is_alive():
        output, _ = _drain_output_pull(session, timeout=timeout, max_bytes=max_bytes)
        term_reason, exit_code, sig = _derive_termination(session, output)
        hints = _enrich_hints(_build_status_hint(alive=False, awaiting_input=False), output, conda_env=session.conda_env)
        return {
            "session_id": session_id,
            "output": output,
            "awaiting_input": False,
            "alive": False,
            "log_path": str(session.logfile_path),
            "conda_env": session.conda_env or "",
            "prompt_pattern": session.prompt_pattern or "",
            "termination_reason": term_reason,
            "exit_code": exit_code,
            "signal": sig,
            "ring_buffer_bytes": session.max_buffer_bytes,
            "ring_buffer_truncated": session.ring_truncated,
            **hints,
        }
    for line in lines:
        try:
            session.process.sendline(line)
            session.last_send_ts = time.time()
            session.mark_activity()
        except Exception:
            break
    output, awaiting_input = _drain_output_pull(session, timeout=timeout, max_bytes=max_bytes)
    alive = session.is_alive()
    if not alive:
        awaiting_input = False
    term_reason, exit_code, sig = _derive_termination(session, output)
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
        "termination_reason": term_reason,
        "exit_code": exit_code,
        "signal": sig,
        "ring_buffer_bytes": session.max_buffer_bytes,
        "ring_buffer_truncated": session.ring_truncated,
        **hints,
    }


def stop_session(session_id: str, kill: bool = False, drop: bool = True) -> Dict[str, object]:
    session = SESSIONS.get(session_id)
    if not session:
        raise ValueError("Sesión no encontrada.")
    if session.is_alive():
        try:
            # Intento de parada suave: Ctrl+C al TTY
            if not kill:
                try:
                    session.process.sendintr()
                except Exception:
                    pass
                time.sleep(0.2)
            # Señales al grupo de procesos para asegurar cierre de hijos
            try:
                pgid = os.getpgid(session.process.pid)
                if not session.process_group_created:
                    raise RuntimeError("Process group was not created for this session.")
                if kill:
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    # Secuencia suave: SIGHUP -> SIGTERM
                    os.killpg(pgid, signal.SIGHUP)
                    time.sleep(0.15)
                    if session.is_alive():
                        os.killpg(pgid, signal.SIGTERM)
            except Exception:
                # Fallback: matar solo el pid
                try:
                    if kill:
                        os.kill(session.process.pid, signal.SIGKILL)
                    else:
                        os.kill(session.process.pid, signal.SIGTERM)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            session.stop_event.set()
            try:
                if session.reader_thread and session.reader_thread.is_alive():
                    session.reader_thread.join(timeout=0.5)
            except Exception:
                pass
            try:
                session.process.close(force=True)
            except Exception:
                pass
    else:
        try:
            session.process.close(force=True)
        except Exception:
            pass
    # Intentar devolver delta pendiente final (si lo hubiera)
    output, _ = _drain_output_pull(session, timeout=0.2, max_bytes=8000)
    term_reason, exit_code, sig = _derive_termination(session, output)
    hints = _enrich_hints(
        _build_status_hint(alive=False, awaiting_input=False),
        output,
        conda_env=session.conda_env,
    )
    if drop:
        SESSIONS.pop(session_id, None)
    return {
        "session_id": session_id,
        "output": output,
        "awaiting_input": False,
        "alive": session.is_alive(),
        "log_path": str(session.logfile_path),
        "conda_env": session.conda_env or "",
        "prompt_pattern": session.prompt_pattern or "",
        "termination_reason": term_reason,
        "exit_code": exit_code,
        "signal": sig,
        "ring_buffer_bytes": session.max_buffer_bytes,
        "ring_buffer_truncated": session.ring_truncated,
        "ring_buffer_discarded_bytes": session.ring_discarded_bytes,
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
    original_command = session.command
    original_conda = session.conda_env
    original_workdir = session.workdir
    original_env = session.env
    original_batch = session.batch_queries
    original_prompt = session.prompt_pattern
    stop_result = stop_session(session_id, kill=False, drop=False)
    session_after_stop = SESSIONS.get(session_id)
    still_alive = bool(stop_result.get("alive")) or bool(
        session_after_stop and session_after_stop.is_alive()
    )
    if still_alive:
        stop_result = stop_session(session_id, kill=True, drop=False)
        session_after_stop = SESSIONS.get(session_id)
        still_alive = bool(stop_result.get("alive")) or bool(
            session_after_stop and session_after_stop.is_alive()
        )
    if still_alive:
        raise RuntimeError("Could not stop previous Python session before restart.")
    SESSIONS.pop(session_id, None)
    return start_session(
        command=original_command,
        conda_env=original_conda,
        workdir=original_workdir,
        env=original_env,
        batch_queries=original_batch,
        prompt_pattern=original_prompt,
        timeout=timeout,
        max_bytes=max_bytes,
    )


__all__ = [
    "start_session",
    "send_input",
    "send_lines",
    "stop_session",
    "restart_session",
]
