# Code_MCP_Tools

VERSION ACTUAL: V3.0

Servidor MCP + panel web orientado a **coding**: expone tools declarativas para RAG, control de CLIs y gestión de memorias/docs/bugs/todos, todo en un único proceso FastAPI/uvicorn con UI integrada.

## Qué incluye la V3.0

- Panel web (`http://127.0.0.1:8000/`): pestañas de Dashboard, RAG, Tools MCP, Memory, Configuration y Logs.
  - Dashboard → Status: muestra modo/modelos, documentos, MCP URL completo, tools activas por grupo y contadores de Memory por proyecto seleccionado.
  - Dashboard → Integrations: instrucciones listas para pegar para Codex CLI, Claude Code y GitHub Copilot (VS Code), con URL actual y botones Copy.
  - Dashboard → AGENTS.md: muestra las guidelines cargadas del backend.
- RAG: reconstrucción desde sitemap o ficheros `txt/` con recarga en caliente del retriever. Rebuild recrea `docs/chunks/metadata` en DuckDB, preservando `projects/items` que ahora viven en SQLite (`data/memory.sqlite3`). MCP expone `hybrid_search` y `chunks_by_url` (dense/lexical opcionales).
  - Nota: el índice RAG es global (no por proyecto). La memoria es por proyecto.
- RAG → Settings: configuración de modo (`local`/`cloud`), embeddings y reranker; persiste en `config.yaml`, requiere Restart MCP y Rebuild del índice.
- Items: tools MCP `store_item`, `update_item`, `get_item`, `list_items`, `search_items`, `patch_doc`, `delete_item`. UI Memory trabaja sobre el mismo servicio. Tipos: `memory`, `doc`, `bug`, `todo` con estados `pending` → `in_progress` → `to_verify` → `resolved`.
- Projects: creación idempotente desde Settings; botón Delete con doble confirmación; no se permite borrar el proyecto activo. Las tools ya no crean proyectos automáticamente (devuelven “Project not found”).
- CLI: tools `cli_start`/`cli_send`/`cli_stop`/`cli_restart` para orquestar sesiones.
- Robustez BD: borrado de proyectos en dos fases (items → proyecto) con FKs activas; sin parches de desactivar FKs.
- Docker: instala PyTorch estándar; si hay GPU disponible, se usará, si no, CPU.

## Requisitos

- Python 3.12
- `pip install -r requirements.txt`
- Conectividad inicial para extensiones DuckDB (`fts`, `vss`) y modelos Qwen.

## Uso rápido

```bash
python app.py
```

- Arranca panel web + servidor MCP (`APP_PORT` 8000, `MCP_HTTP_PATH` `/mcp` por defecto).
- Desde la UI:
  - Dashboard: Status (modo/modelos, docs, MCP URL, tools por grupo, contadores Memory), Integrations (Codex/Claude/Copilot), AGENTS.md.
  - RAG: Ingest (sitemap o ficheros `txt/`) y Settings (modo y modelos; requiere restart + rebuild).
  - Memory: selecciona proyecto, crea items y gestiona estados; edición de metadatos y cuerpo (reemplazo directo en UI; o `patch_doc` por diff desde MCP).
  - Tools MCP: activa/desactiva tools expuestas; requiere Restart MCP.
  - Docs: lista hasta 50 documentos recientes del índice.
Consulta `Extra/Guias/web_ui.md` para detalles y variables de entorno.

## Persistencia y BBDD

- RAG global en DuckDB: `data/rag.duckdb`
- Memoria por proyecto en SQLite: `data/memory.sqlite3`
- Configuración en `config.yaml`:

```yaml
database:          # RAG (DuckDB)
  path: data/rag.duckdb

memory_database:   # Memoria (SQLite)
  path: data/memory.sqlite3
```

Notas de alcance:
- El índice RAG es global (no por proyecto). Un rebuild sustituye el índice global.
- La memoria (projects/items) es por proyecto. Selección en UI → Configuration → Settings.

## Docker (Python 3.12.11)

```bash
docker build -t code-mcp-tools .
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/.cache:/app/.cache \
  -v $(pwd)/txt:/app/txt \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -e APP_HOST=0.0.0.0 \
  -e CONTAINER_NAME=code-mcp-tools \
  --name code-mcp-tools \
  code-mcp-tools
```

- En local el host por defecto es `127.0.0.1` (si no defines `APP_HOST`). En Docker se recomienda `APP_HOST=0.0.0.0` (ya incluido en `docker-compose.yml`). Botón “Restart MCP” reinicia el contenedor si `CONTAINER_NAME` está definido. Logs: `docker logs -f code-mcp-tools`.

### Docker Compose

```bash
docker compose build
docker compose up
```

## Pruebas

```bash
python -m pytest
```

Valida RAG híbrido, BM25 (cuando FTS está disponible) y contrato MCP.
Toda implementación nueva debe incluir un test en `test/` y no se considera lista hasta que pase en verde (AGENTS.md)

## TODO / próximo

- Mejorar soporte FTS/BM25 real en entornos donde la extensión falle (evitar fallback LIKE).
- Forzar refresco de tools en clientes MCP al inicio de sesión.
- (Opcional) Multi-corpus en la misma BD con filtrado por corpus en tools RAG.
