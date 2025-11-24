# Qué aportan
- Permiten a un agente/cliente MCP ejecutar scripts y módulos Python (p. ej. `python -m uvicorn`) de forma interactiva: lanzan el proceso, leen salida incremental, detectan si espera entrada y permiten enviar texto línea a línea.
- Persisten un `session_id` y log opcional en `data/cli_sessions/<id>.log`.
- Python‑only: no ejecuta shell general ni binarios arbitrarios.

## Tools disponibles
- `python_cli_start(mode, script_path/module_name, args, python_opts, conda_env, workdir, timeout, max_bytes, high_scrollback)`: inicia una sesión Python (script o módulo). No ejecuta shell general.
- `python_cli_send(session_id, text, timeout=1.5, max_bytes=16000)`: envía una línea (se añade `\n`) y devuelve la salida nueva (delta).
- `python_cli_stop(session_id, kill=False)`: interrupción suave (Ctrl+C) y señales al grupo; si `kill=True`, SIGKILL.
- `python_cli_restart(session_id, timeout=1.5)`: detiene y relanza usando la misma configuración.

## Configuración
Activa/desactiva cada tool en `config.yaml`:
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

### Validación de `conda_env`
- El nombre del entorno se valida con patrón estricto: letras, dígitos, `_` o `-` (1..64). Ejemplos válidos: `mcp`, `code_tools`, `env-01`.
- Si no necesitas entorno, omite el campo.

## Cómo usar desde el agente
1. `python_cli_start` con `mode=script|module` (ej: `mode=module, module_name=uvicorn`). Opcional: `conda_env: "mcp"`; `workdir` resuelve rutas relativas del script. Revisa `awaiting_input`.
2. Usa `python_cli_send` para interactuar (ej. `"1"`). Lee `awaiting_input`/`alive` antes de enviar más texto.
3. Si quieres terminar, `python_cli_stop`. Para reiniciar limpio, `python_cli_restart`.
4. Consulta `log_path` (si los logs están habilitados en config) para la transcripción.

## Limitaciones y recomendaciones
- Solo Python (script o módulo). Shell general/binaries no están permitidos.
- Scripts deben estar dentro del repo; rutas fuera o symlinks que escapen serán rechazados.
- Las sesiones viven en memoria del proceso; un reinicio del servidor las termina.
- Sesiones inactivas (≥30 minutos) se limpian automáticamente.
- Controla `timeout` y `max_bytes` para streams largos; `high_scrollback` activa un ring buffer mayor.

### Pruebas largas con logs intermitentes
- `test/test_cli_menu.py` incluye una opción lenta con logs a trompicones; útil para validar que `python_cli_send` no cierre la sesión antes de tiempo y que los logs se capturen aunque salgan a pulsos.

### Simulaciones largas tipo LLM
- `test/llm_sim_cli.py` ofrece respuesta corta, lenta (~30s) y salida en fragmentos; sirve para comprobar lecturas prolongadas.
