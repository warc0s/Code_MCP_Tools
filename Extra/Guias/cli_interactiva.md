# Tools CLI interactivas (fastmcp)

## Qué aportan
- Permiten a un agente/cliente MCP interactuar con menús de consola (p. ej. `python app.py`) sin colgarse: lanzan el proceso, leen la salida, detectan si espera entrada y permiten enviar texto línea a línea.
- Persisten un `session_id` y un log en `data/cli_sessions/<id>.log` para auditoría y para reanudar/restart.
- Funcionan sobre el transporte HTTP de `fastmcp`; no hay endpoints manuales.

## Tools disponibles
- `cli_start(command, workdir=None, timeout=1.5, env=None)`: lanza el comando (puedes incluir `conda run -n <env> ...` o definir variables en `env`), devuelve `session_id`, `output` inicial, `awaiting_input`, `alive` y `log_path`.
- `cli_send(session_id, text, timeout=1.5)`: envía una línea (se añade `\n`) y devuelve la salida nueva con los mismos flags.
- `cli_stop(session_id, kill=False)`: envía `SIGINT` (o `SIGKILL` si `kill=True`) y devuelve la salida final.
- `cli_restart(session_id, timeout=1.5)`: detiene y relanza usando el mismo comando/directorio/entorno que la sesión original.

## Configuración
Activa/desactiva cada tool en `config.yaml`:
```yaml
mcp:
  tools:
    hybrid_search: true
    chunks_by_url: true
    cli_start: true
    cli_send: true
    cli_stop: true
    cli_restart: true
```
Si omites las claves `cli_*` quedarán deshabilitadas (cuando se usa `mcp.tools`).

## Cómo usar desde el agente
1. `cli_start` con el comando deseado (ejemplo: `python app.py`). Revisa `awaiting_input`; si es `False` y `alive=True`, quizá necesites enviar un salto de línea.
2. Usa `cli_send` para seleccionar opciones (ej. `"1"` o `"1.2"`). Siempre lee `awaiting_input` y `alive` antes de enviar más texto.
3. Si la CLI se bloquea o quieres terminar, llama a `cli_stop`. Para empezar de cero, `cli_restart`.
4. Consulta `log_path` para revisar la transcripción completa en disco.

## Limitaciones y recomendaciones
- Pensado para CLIs de texto simple (prompts acabados en `>`, `:` o `?`). UIs que limpian pantalla o curses no son soportadas.
- El detector de prompt es heurístico; si `awaiting_input=False` pero ves un prompt en `output`, el cliente debe decidir enviar igualmente.
- Las sesiones viven en memoria del proceso; si el servidor se reinicia, se pierden.
- Controla los timeouts para evitar procesos colgados; el servidor aplica lecturas de salida limitadas a ~16KB por llamada.
