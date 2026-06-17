# Contextarium

Local context layer for coding agents.

CURRENT VERSION: V3.0

Local MCP server and control panel that gives coding agents persistent project context: memory, docs, bugs, todos, RAG search, and controlled tools.

## What V3.0 Includes

- Web panel (`http://127.0.0.1:8000/`): Dashboard, RAG, MCP Tools, Memory, Configuration, and Logs tabs.
  - Dashboard -> Status: shows mode/models, document count, full MCP URL, active tools grouped by category, and Memory counters for the selected project.
  - Dashboard -> Integrations: copy-ready instructions for Codex CLI, Claude Code, and GitHub Copilot (VS Code), with the current URL and Copy buttons.
  - Dashboard -> AGENTS.md: shows the backend-loaded guidelines. Includes info cards (no builder) to remind you which sections to remove or adjust before copying.
- RAG: rebuild from sitemap or `txt/` files with hot retriever reload. Rebuild recreates `docs/chunks/metadata` in DuckDB while preserving `projects/items`, which now live in SQLite (`data/memory.sqlite3`). MCP exposes `hybrid_search` and `chunks_by_url` (dense/lexical are optional).
  - Note: the RAG index is global (not project-scoped). Memory is project-scoped.
- RAG -> Settings: mode (`local`/`cloud`), embeddings, and reranker configuration; persists to `config.yaml` and requires Restart MCP plus index Rebuild.
- Items: MCP tools `store_item`, `update_item`, `get_item`, `list_items`, `search_items`, `patch_doc`, and `delete_item`. The Memory UI uses the same service. Types: `memory`, `doc`, `bug`, `todo` with statuses `pending` -> `in_progress` -> `to_verify` -> `resolved`.
  - Body is editable for every type from the inline UI editor.
  - Simplified metadata architecture:
    - Required per-type fields are sent in `typed` (for example bug: `severity,reproduction,expected,root_cause`; todo: `kind,acceptance_criteria,priority`; memory: `topic,decision,context,rationale`; doc: optional `authors,related_docs`).
    - `meta` (JSON) is reserved for optional extras (logs, screenshots, resolution_criteria, related_files, done_summary, etc.).
    - Resolution enforcement: bug/todo items must include `meta.done_summary` (>=120 chars) and `meta.related_files` (>=1).
  - The UI shows typed inputs and keeps `Meta (JSON)` as an advanced optional block; the template is auto-applied when switching subtype.
- Projects: idempotent creation from Settings; Delete button with double confirmation; deleting the active project is blocked. Tools no longer auto-create projects (they return `Project not found`).
- Python CLI: `python_cli_start` / `python_cli_send` / `python_cli_stop` / `python_cli_restart` for interactive Python sessions (script or module). It does not run a general shell.
- DB robustness: project deletion runs in two phases (items -> project) with active FKs; no FK-disabling shortcuts.
- Docker: installs standard PyTorch; GPU is used when available, otherwise CPU.

## Requirements

- Python 3.12
- `pip install -r requirements.txt`
- Initial connectivity for DuckDB extensions (`fts`, `vss`) and local models (`voyageai/voyage-4-nano`, `Qwen/Qwen3-Reranker-0.6B`).

## Quick Start

```bash
python app.py
```

- Starts the web panel and MCP server (`APP_PORT` 8000, `MCP_HTTP_PATH` `/mcp` by default).
- From the UI:
  - Dashboard: Status (mode/models, docs, MCP URL, tools by group, Memory counters), Integrations (Codex/Claude/Copilot), AGENTS.md.
  - RAG: Ingest (sitemap or `txt/` files) and Settings (mode and models; requires restart + rebuild).
  - Memory: select a project, create items, manage statuses, and edit metadata/body (direct replacement in UI; or `patch_doc` by diff from MCP).
  - MCP Tools: enable/disable exposed tools; requires Restart MCP.
  - Docs: lists up to 50 recent documents from the index.

See `Extra/Guias/web_ui.md` for details and environment variables.

## Persistence And Databases

- Global RAG in DuckDB: `data/rag.duckdb`
- Project-scoped Memory in SQLite: `data/memory.sqlite3`
- Configuration in `config.yaml`:

```yaml
database:          # RAG (DuckDB)
  path: data/rag.duckdb

memory_database:   # Memory (SQLite)
  path: data/memory.sqlite3
```

Scope notes:
- The RAG index is global (not project-scoped). A rebuild replaces the global index.
- Memory (`projects/items`) is project-scoped. Selection lives in UI -> Configuration -> Settings.

## Docker (Python 3.12.11)

```bash
docker build -t contextarium-tools .
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/.cache:/app/.cache \
  -v $(pwd)/txt:/app/txt \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -e APP_HOST=0.0.0.0 \
  -e CONTAINER_NAME=contextarium-tools \
  --name contextarium-tools \
  contextarium-tools
```

- Locally, the default host is `127.0.0.1` unless `APP_HOST` is set. In Docker, `APP_HOST=0.0.0.0` is recommended and already included in `docker-compose.yml`. The “Restart MCP” button restarts the container when `CONTAINER_NAME` is set. Logs: `docker logs -f contextarium-tools`.

### Docker Compose

```bash
docker compose build
docker compose up
```

## Tests

```bash
python -m pytest
```

Validates hybrid RAG, BM25 when FTS is available, the MCP contract, and per-type meta models.

Item JSON Schema in MCP tools:
- `store_item` and `update_item` expose `typed` (oneOf per type; required in `store_item` for memory/bug/todo) and `meta` (optional oneOf). Clients can build valid payloads without long required JSON blobs.

## TODO / Next

- Improve real FTS/BM25 support in environments where the extension fails (avoid LIKE fallback).
- Force MCP clients to refresh tools at session start.
- Optional: multi-corpus support in the same DB with corpus filtering in RAG tools.
