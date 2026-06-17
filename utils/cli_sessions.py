"""
Interactive CLI session management using pexpect (single pexpect-only backend).

Key hardening:
- Background drainer per session that continuously reads the PTY and accumulates
  output in an in-memory ring buffer, byte-limited (best-effort, non-blocking).
- Real per-session `last_activity` and periodic cleanup.
- More robust signals: soft interruption (Ctrl+C) and process-group stops;
  tolerates EOF and EIO on macOS.
- Configurable default TTY size to reduce odd CLI wrapping.

Notes:
- The public API (start_session, send_input, stop_session, restart_session)
  remains stable. `max_bytes` support was added to limit reads per call
  (delta since the last pull), and prompt detection is decoupled from logs.
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
# Default sizes and limits.
DEFAULT_RING_MAX_BYTES = int(os.getenv("CLI_RING_BUFFER_MAX_BYTES", str(512 * 1024)))  # 512 KiB
DEFAULT_RING_MAX_BYTES_HIGH = int(os.getenv("CLI_RING_BUFFER_MAX_BYTES_HIGH", str(2 * 1024 * 1024)))  # 2 MiB
READ_CHUNK_BYTES = int(os.getenv("CLI_READ_CHUNK_BYTES", str(32 * 1024)))  # 32 KiB per read
DEFAULT_INACTIVITY_TTL = int(os.getenv("CLI_INACTIVITY_TTL_SEC", str(30 * 60)))  # 30 minutes (inactive-session GC)
# Session timeouts (apply to any mode; recommended for REPL).
DEFAULT_SESSION_LIFETIME_SEC = int(os.getenv("CLI_SESSION_LIFETIME_SEC", str(30 * 60)))  # 30 min total lifetime
DEFAULT_IDLE_TIMEOUT_SEC = int(os.getenv("CLI_IDLE_TIMEOUT_SEC", str(15 * 60)))  # 15 min without interaction
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
    Simple heuristic to mark whether the CLI is waiting for input.
    """
    stripped = text.rstrip()
    if not stripped:
        return False
    if prompt_pattern:
        try:
            if re.search(prompt_pattern, stripped):
                return True
        except re.error:
            # If the pattern is invalid, fall back to the heuristic.
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
    # If the last line is empty but the previous one ends in a prompt, treat it as awaiting_input.
    if len(lines) >= 2 and not tail.strip():
        prev = lines[-2]
        if any(prev.endswith(suffix) for suffix in prompt_suffixes):
            return True
    return False


def _build_status_hint(alive: bool, awaiting_input: bool) -> Dict[str, str]:
    if not alive:
        return {
            "status_hint": "Session terminated.",
            "next_step": "Restart with python_cli_restart or start a new one with python_cli_start.",
        }
    if awaiting_input:
        return {
            "status_hint": "Waiting for your input.",
            "next_step": "Send input with python_cli_send.",
        }
    return {
        "status_hint": "Process is running and is not asking for input yet.",
        "next_step": "Call python_cli_send again (empty text allowed) after a few seconds to read more output.",
    }


def _enrich_hints(hints: Dict[str, str], output: str, conda_env: Optional[str]) -> Dict[str, str]:
    """
    Add contextual guidance for common failures (dependencies or network).
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
            "If a package is missing, ask whether to use another conda environment (conda_env parameter) or install it before relaunching."
        )
    if network_issue:
        advice.append(
            "If the script needs internet (LLM/APIs), ask whether it can be launched with network permissions or how to enable access."
        )
    if eof_issue:
        advice.append(
            "EOF was detected while reading input; use stdin_lines to send initial input or confirm the command has a TTY available."
        )
    if conda_env and (dependency_issue or network_issue or eof_issue):
        advice.append(f"Use conda_env='{conda_env}' if that is the expected environment.")

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
    # Ring buffer (pending to send to the client) and synchronization.
    pending_chunks: deque[str] = field(default_factory=deque)
    pending_bytes: int = 0
    max_buffer_bytes: int = DEFAULT_RING_MAX_BYTES
    last_activity: float = field(default_factory=time.time)
    rows: int = DEFAULT_TTY_ROWS
    cols: int = DEFAULT_TTY_COLS
    reader_thread: Optional[threading.Thread] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    # Auxiliary fields.
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
            # Do not interfere with the flow if logging fails.
            pass

    def append_output(self, text: str) -> None:
        if not text:
            return
        with self.lock:
            self.pending_chunks.append(text)
            self.pending_bytes += len(text.encode("utf-8", errors="ignore"))
            # Trim to maximum size, discarding oldest data.
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
        """Return and clear up to max_bytes from the pending queue.

        If more than max_bytes is pending, return the first max_bytes and keep
        the excess for future reads.
        """
        with self.lock:
            if self.pending_bytes <= 0 or not self.pending_chunks:
                return ""
            out_parts: list[str] = []
            budget = max(1, int(max_bytes))
            # Consume chunks while there is budget.
            while self.pending_chunks and budget > 0:
                chunk = self.pending_chunks[0]
                chunk_bytes = len(chunk.encode("utf-8", errors="ignore"))
                if chunk_bytes <= budget:
                    out_parts.append(chunk)
                    self.pending_chunks.popleft()
                    self.pending_bytes -= chunk_bytes
                    budget -= chunk_bytes
                else:
                    # Take a chunk slice and keep the rest at the head.
                    # Convert to bytes for exact slicing and decode tolerantly.
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
    Start a reader thread that drains the session PTY into the ring buffer.
    Treat EOF and EIO (common in PTYs on close) as normal termination.
    """
    def _reader() -> None:
        try:
            # Adjust TTY size to reduce odd wrapping.
            try:
                session.process.setwinsize(session.rows, session.cols)
            except Exception:
                pass
            while not session.stop_event.is_set():
                # If the process is no longer alive, try one final read and exit.
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
                            # Treat EIO as PTY EOF.
                            pass
                    break
                try:
                    chunk = session.process.read_nonblocking(size=READ_CHUNK_BYTES, timeout=0.4)
                    if chunk:
                        session.append_output(chunk)
                        if session.log_enabled:
                            session.append_log(chunk)
                    else:
                        # Nothing read; short pause.
                        time.sleep(0.05)
                except pexpect.TIMEOUT:
                    # No data in this cycle.
                    continue
                except pexpect.EOF:
                    break
                except OSError as exc:
                    if getattr(exc, "errno", None) == errno.EIO:
                        session.eio_error = True
                        break
                    # Other errors: avoid blocking the thread.
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
    Ensure the script path (when applicable) is absolute and exists.
    """
    if not tokens:
        return tokens

    script_index: Optional[int] = None
    # Direct case: the interpreter is invoked with a .py script directly.
    if tokens[0].endswith(".py"):
        script_index = 0
    # 'python ... <script>.py ...' case: locate the first .py token.
    elif tokens[0].startswith("python"):
        for i in range(1, len(tokens)):
            tok = tokens[i]
            # Avoid flags such as -c/-m/-u.
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
        f"Script {script_candidate} not found. Adjust workdir, use an absolute path, or fix the command."
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
    Build (executable, argv) for shell-free spawn.
    """
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ValueError("Command contains invalid quotes or escapes.") from exc
    tokens = _resolve_script_path(tokens, workdir)
    if not tokens:
        raise ValueError("Command is empty after parsing.")
    first = tokens[0]
    pyexec = _resolve_python_executable(conda_env)
    if pyexec.startswith("conda:run:-n:"):
        envname = pyexec.split(":")[-1]
        return "conda", ["run", "-n", envname] + tokens
    # Replace python front if present.
    if first in {"python", "python3"} or first.endswith("python") or first.endswith("python3"):
        return pyexec, tokens[1:]
    if first.endswith(".py"):
        return pyexec, tokens
    # Otherwise return as-is (should still be Python-only by policy).
    return first, tokens[1:]


def _cleanup_sessions(max_age_seconds: int = DEFAULT_INACTIVITY_TTL) -> None:
    """
    Close dead or very old processes to avoid leaks and hangs.
    """
    now = time.time()
    for session_id, session in list(SESSIONS.items()):
        # Use last_activity for fairer GC.
        expired = (now - session.last_activity) > max_age_seconds
        alive = False
        try:
            alive = session.is_alive()
        except Exception:
            alive = False

        # Grace: do not delete for 'not alive' if the session is very recent.
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
        # Soft signal to the group when possible.
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
    Wait up to `timeout` to accumulate new output in the ring buffer and return
    up to `max_bytes` from the pending delta. Marks awaiting_input by heuristic.
    """
    deadline = time.time() + max(0.0, float(timeout))
    # Short active wait: exit once data exists or on expiry.
    while time.time() < deadline:
        with session.lock:
            have_data = session.pending_bytes > 0
        if have_data and stop_on_first_data:
            break
        # If the process already ended and there is no data, exit.
        if not session.is_alive():
            break
        time.sleep(0.05)
    text = session.pull_output(max_bytes=max_bytes)
    awaiting_input = False
    # awaiting_input is only reliable in REPL (prompt >>> or ...).
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
    Start an interactive CLI session and return initial output.
    """
    _cleanup_sessions()
    if len(SESSIONS) >= MAX_SESSIONS:
        raise RuntimeError("Maximum number of sessions reached. Close one before opening another.")
    cleaned = (command or "").strip()
    if not cleaned:
        raise ValueError("You must provide a command to start the session.")
    if batch_queries is not None:
        if not isinstance(batch_queries, list) or not all(isinstance(item, str) for item in batch_queries):
            raise ValueError("batch_queries must be a list of strings.")
    if stdin_lines is not None:
        if not isinstance(stdin_lines, list) or not all(isinstance(item, str) for item in stdin_lines):
            raise ValueError("stdin_lines must be a list of strings.")
    if prompt_pattern is not None and not isinstance(prompt_pattern, str):
        raise ValueError("prompt_pattern must be a string with a regular expression.")
    # Validate conda env defensively (prevents shell injection and common mistakes)
    try:
        conda_env = _validate_conda_env(conda_env)
    except ValueError as exc:
        # Provide actionable advice consistent with other hints
        raise ValueError(
            f"{exc} If you do not need a conda env, omit the field. If you do, create it first and try again."
        ) from exc

    # Always spawn directly to allow stdin_lines without a shell.
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

        # Create a new process group (POSIX) for group signals.
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
            "Could not launch the command. Verify the command, check the conda environment "
            "(use only letters/digits/_/-), or install dependencies before retrying."
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
    # Adjust TTY and start drainer.
    _start_reader_thread(session)
    # Pre-inject stdin lines when provided.
    if stdin_lines:
        for line in stdin_lines:
            try:
                session.process.sendline(line)
                session.last_send_ts = time.time()
                session.mark_activity()
            except Exception:
                break
    # Wait briefly and return accumulated delta.
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
    # Look up first without cleanup to avoid deleting a freshly created session by mistake.
    session = SESSIONS.get(session_id)
    if not session:
        # Cleanup and try to locate the session again (single retry).
        _cleanup_sessions()
        session = SESSIONS.get(session_id)
    if not session:
        raise ValueError("Session not found. Start a session before sending input.")
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
        raise ValueError("Session not found. Start a session before sending input.")
    if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
        raise ValueError("stdin_lines must be a list of strings.")
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
        raise ValueError("Session not found.")
    if session.is_alive():
        try:
            # Soft stop attempt: Ctrl+C to the TTY.
            if not kill:
                try:
                    session.process.sendintr()
                except Exception:
                    pass
                time.sleep(0.2)
            # Process-group signals to ensure child processes close.
            try:
                pgid = os.getpgid(session.process.pid)
                if not session.process_group_created:
                    raise RuntimeError("Process group was not created for this session.")
                if kill:
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    # Soft sequence: SIGHUP -> SIGTERM.
                    os.killpg(pgid, signal.SIGHUP)
                    time.sleep(0.15)
                    if session.is_alive():
                        os.killpg(pgid, signal.SIGTERM)
            except Exception:
                # Fallback: kill only the PID.
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
    # Try to return final pending delta when available.
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
        raise ValueError("Session not found.")
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
