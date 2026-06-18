# Contextarium Web Panel

Contextarium is a local context layer for coding agents: a local MCP server plus a control panel for persistent memory, docs, bugs, todos, RAG search, and controlled tools.

The web panel exposes the local control surface in the same process as the MCP server. HTML is served from `templates/index.html` (backend in `app.py`).

## Startup

- Run `python app.py`.
- Optional variables:
  - `APP_HOST` (default `127.0.0.1`; in Docker, `0.0.0.0` is usually used to expose the port)
  - `APP_PORT` (default `8000`)
  - `MCP_HTTP_PATH` (default `/mcp`)
- The panel lives at the root (`http://HOST:PORT/`) and the MCP endpoint at `http://HOST:PORT<MCP_HTTP_PATH>`.

- **Dashboard**: quick status read live from the backend; Refresh buttons.
  - Subtabs: **Status**, **Integrations**, **AGENTS.md**.
  - Status: shows `mode`, `embedding`, `reranker`, `docs_count`, full `MCP URL`, active tools grouped by group (`rag`, `items`), and a Memory card with the active project and counters by type.
    - Scope note: `docs_count` is global (global RAG). Memory counters depend on the active project.
    - The main pill distinguishes `RAG Ready`, `RAG Needs Rebuild`, and `RAG Not Ready`; an open DB does not imply the retriever is compatible with the current config.
  - Integrations: concise instructions for Codex CLI, Claude Code, and GitHub Copilot (VS Code) with copy buttons and the current URL.
  - AGENTS.md: renders backend guidelines (`/ui/api/guidelines`).
    - Info cards: reminders for Context7 MCP, Chrome DevTools (MCP) as an optional integration, project name, RAG, Items/Memory, and the external expert agent. Remove sections that do not apply from your AGENTS.md copy.
- **RAG**: subtabs **Status**, **Ingest**, and **Settings**.
  - Settings: configure mode (`local`/`cloud`), embeddings, and reranker. It writes to `config.yaml`, marks `needs_restart` + `needs_rebuild`, and requires restart plus index rebuild to apply.
  - Scope note: the RAG index is global (not per project). A rebuild replaces the global index.
- **MCP Tools**: management of exposed tools. Pressing Save writes changes to `config.yaml` (`mcp.tools` or `mcp.tool_sets`, depending on what exists); changes are not hot-applied. **Restart MCP** relaunches the process with the newly saved config. MCP clients must call `tools/list` again after restart.
  - Available groups: `rag` and `items` (for project/memory/doc/bug/todo tools).
- **Memory**: tab with internal type tabs (`memory`, `doc`, `bug`, `todo`), item creation, Kanban board (statuses `pending` -> `in_progress` -> `to_verify` -> `resolved` with drag & drop), metadata editing, direct body editing, read-only detail modals, and item deletion.
  - Scope note: Memory is project-scoped; select/create the active project in Configuration -> Settings.
  - Project management: in the project selection card you will see the list with `Use` and `Delete` buttons. Deleting the active project is not allowed. From this version, the `Delete` button remains enabled even for the active project and shows an error toast when pressed: "You cannot delete the active project. Change the selection first." When deleting any other project, the UI shows a double English confirmation warning that all associated items (memory/doc/bug/todo) will be deleted and the action cannot be undone.
  - The backend canonicalizes slugs before deleting, so equivalent variants such as underscores vs dashes cannot bypass active-project protection.
- **Settings**: only the project selection card remains here (create/activate, list, and delete with confirmations). RAG settings are under **RAG -> Settings**.
- **Ingest**: rebuild from sitemap or from `txt/` files (one URL per line; `#` for comments). Replaces the current DB and hot-reloads the retriever.
- **Docs**: lists up to 50 recent documents (doc_id, title, URL, date) from the read-only DB.
- **Log**: web client transcripts (UI actions). It does not replace the server log (`stdout` from `python app.py`).

## Behavior And Limits

- Rebuilds block concurrent rebuilds (409 when one is already running). The previous connection is closed before regenerating the DB to avoid locks, and the retriever is hot-reloaded when finished.
- Rebuild progress initializes defensively: any late callback or direct progress update can update state even when no previous snapshot exists.
- If the DB does not exist at startup, the panel remains available; RAG tools return a friendly error until the index is rebuilt.
- The configuration tab shows a dynamic `Config changed; rebuild the index...` warning when the backend marks `needs_rebuild=true` (for example after changing models or mode from the UI).
- During a rebuild (ingestion), the header shows a `Rebuilding...` pill and the UI receives live progress through SSE (`/ui/api/rebuild/events`) to avoid aggressive `/ui/api/status` polling. When finished, the stream closes and a completion toast is shown.
  - You can also press "Refresh" manually when needed.
  - The backend can use GPU automatically for embeddings if Torch detects CUDA.
  - Ingestion buttons (`Index from Sitemap` and `Index from File`) show a loading state (spinner) on the button itself during the operation.
- Document counts and URLs listed in Dashboard/RAG are read directly from the DB; if you change the index (rebuild) or close the connection, data updates on the next Refresh.
- The header shows `Restart pending` when saved `config.yaml` changes require restart.
- In Docker mode, **Restart MCP** runs `docker restart <CONTAINER_NAME>` (default `contextarium-tools` in `docker-compose.yml`). You can also restart the container manually and inspect logs with `docker logs -f contextarium-tools`.
  - You must set `CONTAINER_NAME` (already included in `docker-compose.yml`) for the button to work; there is no fallback that relaunches subprocesses outside Docker.
  - Timeout is configurable with `DOCKER_RESTART_TIMEOUT_SEC` (default 30s).

## Recent Modularization

- Split HTML: `templates/index.html` extends `templates/base.html` and includes tabs from `templates/partials/`.
- Styles moved out of HTML: `static/css/app.css`.
- JS by domain: `static/js/main.js` (navigation/tabs) and tab modules in `static/js/tabs/`, backed by helpers in `static/js/core/`.
- Assets are served through `/static` mounted in FastAPI; use `url_for('static', path='...')` to reference CSS/JS.

## MCP

- The MCP server shares the FastAPI process with the UI. Tools are registered from `config.yaml` or panel toggles.
- JSON-RPC output remains the same (`tools/list`, `tools/call`), including `outputSchema`.
