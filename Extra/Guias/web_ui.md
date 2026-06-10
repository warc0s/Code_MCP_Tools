# Panel web Contextarium

Contextarium es una capa local de contexto para agentes de coding: servidor MCP local y panel de control para memoria persistente, docs, bugs, todos, búsqueda RAG y tools controladas.

El panel web ofrece las mismas capacidades que la antigua CLI, pero expuestas de forma gráfica y en el mismo proceso que el servidor MCP. HTML servido desde `templates/index.html` (backend puro en `app.py`).

## Arranque
- Ejecuta `python app.py`.
- Variables opcionales:
  - `APP_HOST` (por defecto `127.0.0.1`; en Docker suele usarse `0.0.0.0` para exponer el puerto)
  - `APP_PORT` (por defecto `8000`)
  - `MCP_HTTP_PATH` (por defecto `/mcp`)
- El panel vive en la raíz (`http://HOST:PORT/`) y el endpoint MCP en `http://HOST:PORT<MCP_HTTP_PATH>`.

- **Dashboard**: estado rápido leído en tiempo real desde el backend; botones de Refresh.
  - Subpestañas: **Status**, **Integrations**, **AGENTS.md**.
  - Status: muestra `mode`, `embedding`, `reranker`, `docs_count`, `MCP URL` completo, tools activas agrupadas por grupo (`rag`, `python_cli`, `items`) y tarjeta Memory con proyecto activo y contadores por tipo.
    - Nota de ámbito: `docs_count` es global (RAG global). Los contadores de Memory dependen del proyecto activo.
  - Integrations: instrucciones concisas para Codex CLI, Claude Code y GitHub Copilot (VS Code) con botones de copiar y URL actual.
  - AGENTS.md: renderiza las guidelines del backend (`/ui/api/guidelines`).
    - Tarjetas informativas: recordatorios para Context7 MCP, Chrome DevTools (MCP) como integración opcional, nombre de proyecto, RAG, Items/Memory y agente experto externo. Elimina en tu copia de AGENTS.md las secciones que no apliquen.
- **RAG**: subpestañas **Status**, **Ingest** y **Settings**.
  - Settings: configurar modo (`local`/`cloud`), embeddings y reranker. Se guarda en `config.yaml`, marca `needs_restart` + `needs_rebuild`; requiere reinicio y reconstrucción del índice para aplicar.
  - Nota de ámbito: el índice RAG es global (no por proyecto). Un rebuild sustituye el índice global.
- **Tools MCP**: gestión de tools expuestas. Los cambios al pulsar Save se guardan en `config.yaml` (rama `mcp.tools` o `mcp.tool_sets` según exista); no se aplican en caliente. El botón **Restart MCP** relanza el proceso con la config recién guardada. Los clientes MCP deben volver a llamar a `tools/list` tras el reinicio.
  - Grupos disponibles: `rag`, `python_cli` y `items` (para las nuevas tools de proyectos/memories/docs/bugs/todos).
- **Memory**: pestaña con tab interno por tipo (`memory`, `doc`, `bug`, `todo`), selección/creación de proyecto, creación de items, tablero estilo Kanban (estados `pending` → `in_progress` → `to_verify` → `resolved` con drag & drop), edición de metadatos y patch de docs con diff unificado. También permite borrar items.
  - Nota de ámbito: Memory es por proyecto; selecciona/crea el proyecto activo en Configuration → Settings.
  - Gestión de proyectos: en la tarjeta de selección de proyecto verás el listado con botones `Use` y `Delete`. No se permite borrar el proyecto activo. A partir de esta versión, el botón `Delete` se mantiene habilitado también para el proyecto activo y, al pulsarlo, la UI muestra un toast de error informando: “You cannot delete the active project. Change the selection first.” (quedando claro el motivo). Al borrar cualquier otro proyecto, se muestra doble confirmación en inglés avisando de que se eliminarán todos los items asociados (memory/doc/bug/todo) y que no hay vuelta atrás.
- **Settings**: aquí solo queda la tarjeta de selección de proyecto (crear/activar, lista y borrado con confirmaciones). Los ajustes de RAG están en **RAG → Settings**.
- **Ingesta**: reconstrucción por sitemap o por ficheros de `txt/` (una URL por línea; `#` como comentario). Sustituye la BD actual y recarga el retriever en caliente.
- **Docs**: lista hasta 50 documentos recientes (doc_id, título, URL, fecha) obtenidos de la BD en solo lectura.
- **Log**: transcripciones del cliente web (acciones de la UI). No sustituye el log del servidor (`stdout` de `python app.py`).

## Comportamiento y límites
- Reconstrucciones bloquean concurrentes (409 si ya hay una en curso). Se cierra la conexión previa antes de regenerar la BD para evitar bloqueos, y al finalizar se recarga el retriever en caliente.
- Si no existe la BD al iniciar, el panel sigue disponible; las tools RAG devolverán error amigable hasta que se reconstruya.
- Sesiones CLI inactivas o muy antiguas (>30 minutos) se limpian automáticamente para evitar fugas.
- Python CLI: sesiones orientadas a Python (script o módulo). No ejecuta shell general.
- El tab de configuración muestra un aviso dinámico `Config changed; rebuild the index...` cuando el backend marca `needs_rebuild=true` (p. ej. tras cambiar modelos o modo desde la propia UI).
- Durante una reconstrucción (ingesta) el header muestra un pill `Rebuilding...` y la UI recibe progreso en vivo vía SSE (`/ui/api/rebuild/events`) para evitar polling agresivo de `/ui/api/status`. Al terminar se cierra el stream y se muestra un toast de finalización.
  - También puedes pulsar “Refresh” manual cuando lo necesites.
  - El backend puede usar GPU automáticamente para generar embeddings si Torch detecta CUDA.
  - Los botones de ingesta (`Index from Sitemap` y `Index from File`) muestran estado de carga (spinner) sobre el propio botón durante la operación.
- El recuento de documentos y las URLs listadas en Dashboard/RAG se leen directamente de la BD; si cambias de índice (rebuild) o cierras la conexión, los datos se actualizarán en el siguiente Refresh.
- El header muestra `Restart pending` cuando hay cambios guardados en `config.yaml` que requieren reinicio.
- En modo Docker, el botón **Restart MCP** ejecuta `docker restart <CONTAINER_NAME>` (por defecto `contextarium-tools` en `docker-compose.yml`). También puedes reiniciar el contenedor a mano y consultar logs con `docker logs -f contextarium-tools`.
  - Debes establecer `CONTAINER_NAME` (ya incluido en `docker-compose.yml`) para que el botón funcione; no hay fallback a relanzar subprocesos fuera de Docker.
  - Timeout configurable con `DOCKER_RESTART_TIMEOUT_SEC` (por defecto 30s).

## Modularización reciente
- HTML dividido: `templates/index.html` extiende `templates/base.html` e incluye pestañas en `templates/partials/`.
- Estilos fuera del HTML: `static/css/app.css`.
- JS por dominio: `static/js/main.js` (navegación/tabs) y módulos por pestaña en `static/js/tabs/` apoyados en helpers de `static/js/core/`.
- Assets servidos vía `/static` montado en FastAPI; usa `url_for('static', path='...')` para referenciar CSS/JS.

## MCP
- El servidor MCP comparte proceso FastAPI con la UI. Tools registradas según `config.yaml` o los toggles del panel.
- Output JSON-RPC sigue igual (`tools/list`, `tools/call`), con `outputSchema` incluido.
