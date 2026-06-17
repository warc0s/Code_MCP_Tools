# What It Provides

- Lets an agent/MCP client run Python scripts and modules (for example `python -m uvicorn`) interactively: start the process, read incremental output, detect whether it is waiting for input, and send text line by line.
- Persists a `session_id` and optional log in `data/cli_sessions/<id>.log`.
- Python-only: it does not run a general shell or arbitrary binaries.

## Available Tools

- `python_cli_start(mode, script_path/module_name, args, python_opts, conda_env, workdir, timeout, max_bytes, high_scrollback, stdin_lines)`: starts a Python session (script, module, or `module_repl`). You can pre-inject input with `stdin_lines` (one line per input). It does not run a general shell.
- `python_cli_send(session_id, text?, stdin_lines?, timeout=1.5, max_bytes=16000)`: sends one line (`text`) or several (`stdin_lines`) and returns new output (delta). `text` is optional.
- `python_cli_stop(session_id, kill=False)`: soft interruption (Ctrl+C) and process-group signals; if `kill=True`, SIGKILL.
- `python_cli_restart(session_id, timeout=1.5)`: stops and relaunches with the same configuration. It first tries a soft stop; if the process is still alive it escalates to `kill=True` and aborts the restart if termination still cannot be confirmed.

## Configuration

Enable/disable each tool in `config.yaml`:

```yaml
mcp:
  tools:
    hybrid_search: true
    chunks_by_url: true
    python_cli_start: true
    python_cli_send: true
    python_cli_stop: true
    python_cli_restart: true
```

### `conda_env` Validation

- The environment name is validated with a strict pattern: letters, digits, `_`, or `-` (1..64). Valid examples: `mcp`, `code_tools`, `env-01`.
- If you do not need an environment, omit the field.

## How To Use From An Agent

1. Call `python_cli_start` with `mode=script|module|module_repl` (example: `mode=module, module_name=uvicorn`). Optional: `conda_env: "mcp"`; `workdir` resolves relative script paths. If the script uses `input()`, add `stdin_lines`.
2. Use `python_cli_send` to interact (for example `"1"` or `stdin_lines: ["user", "pass"]`). Read `awaiting_input`/`alive` before sending more text.
3. When done, call `python_cli_stop`. For a clean restart, call `python_cli_restart`.
4. Check `log_path` (if logs are enabled in config) and state fields (`termination_reason`, `exit_code`, `signal`, `ring_buffer_*`).

## Limits And Recommendations

- Python only (script or module). General shell/binaries are not allowed.
- Scripts must be inside the repo; outside paths or escaping symlinks are rejected. Errors include `repo_root`, `workdir`, and `resolved` for diagnosis.
- Sessions live in process memory; a server restart terminates them.
- Inactive sessions (>=30 minutes) are cleaned automatically.
- Tune `timeout` and `max_bytes` for long streams; `high_scrollback` enables a larger ring buffer.

### Long Tests With Intermittent Logs

- `test/test_cli_menu.py` includes a slow option with bursty logs; it is useful to validate that `python_cli_send` does not close the session too early and that logs are captured even when they arrive in pulses.

### Long LLM-Style Simulations

- `test/llm_sim_cli.py` provides short, slow (~30s), and fragmented output; it helps validate prolonged reads.

## State And Diagnostics

- Whenever `alive=false`, `awaiting_input=false`.
- `termination_reason` can be `Running|Exited|Signaled|EOF_on_stdin|UnknownError` with `exit_code`/`signal` when applicable.
- If you see `EOF_on_stdin` in scripts with `input()`, provide `stdin_lines` or use a non-interactive flow.
- Timeouts: sessions can finish by `Timeout` after total lifetime (30 min by default) or inactivity (15 min by default). Values are configurable by environment (`CLI_SESSION_LIFETIME_SEC`, `CLI_IDLE_TIMEOUT_SEC`).

## Conda Environments And Shell-Free Execution

- The tool does not use `bash -lc`; it spawns the Python interpreter directly with argv.
- If you pass `conda_env`, it tries to resolve that environment's `python` with `conda run -n <env> python -c 'import sys; print(sys.executable)'` and launches that binary; if this fails, it falls back to `conda run -n <env> python ...` without a shell.
- `requirements` must be installed in the selected conda environment for scripts/modules to see them.
