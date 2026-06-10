# Contextarium

Local context layer for coding agents.

VERSION ACTUAL: V3.0

Local MCP server and control panel that gives coding agents persistent project context: memory, docs, bugs, todos, RAG search and controlled tools.

## Qué incluye la V3.0

- Panel web (`http://127.0.0.1:8000/`): pestañas de Dashboard, RAG, Tools MCP, Memory, Configuration y Logs.
  - Dashboard → Status: muestra modo/modelos, documentos, MCP URL completo, tools activas por grupo y contadores de Memory por proyecto seleccionado.
  - Dashboard → Integrations: instrucciones listas para pegar para Codex CLI, Claude Code y GitHub Copilot (VS Code), con URL actual y botones Copy.
  - Dashboard → AGENTS.md: muestra las guidelines cargadas del backend. Incluye tarjetas informativas (no hay builder) para recordar qué secciones quitar/ajustar al copiar.
- RAG: reconstrucción desde sitemap o ficheros `txt/` con recarga en caliente del retriever. Rebuild recrea `docs/chunks/metadata` en DuckDB, preservando `projects/items` que ahora viven en SQLite (`data/memory.sqlite3`). MCP expone `hybrid_search` y `chunks_by_url` (dense/lexical opcionales).
  - Nota: el índice RAG es global (no por proyecto). La memoria es por proyecto.
- RAG → Settings: configuración de modo (`local`/`cloud`), embeddings y reranker; persiste en `config.yaml`, requiere Restart MCP y Rebuild del índice.
- Items: tools MCP `store_item`, `update_item`, `get_item`, `list_items`, `search_items`, `patch_doc`, `delete_item`. UI Memory trabaja sobre el mismo servicio. Tipos: `memory`, `doc`, `bug`, `todo` con estados `pending` → `in_progress` → `to_verify` → `resolved`.
  - Body editable en todos los tipos desde el editor inline de la UI.
  - Arquitectura de metadatos simplificada:
    - Campos obligatorios por tipo se envían en `typed` (p. ej., bug: `severity,reproduction,expected,root_cause`; todo: `kind,acceptance_criteria,priority`; memory: `topic,decision,context,rationale`; doc: `authors,related_docs` opcionales).
    - `meta` (JSON) queda para extras opcionales (logs, screenshots, resolution_criteria, related_files, done_summary, etc.).
    - Enforcement al resolver: bug/todo deben incluir `meta.done_summary` (≥120 chars) y `meta.related_files` (>=1).
  - La UI muestra inputs tipados y deja `Meta (JSON)` como bloque avanzado (opcional); se autoaplica la plantilla al cambiar de subtipo.
- Projects: creación idempotente desde Settings; botón Delete con doble confirmación; no se permite borrar el proyecto activo. Las tools ya no crean proyectos automáticamente (devuelven “Project not found”).
- Python CLI: tools `python_cli_start` / `python_cli_send` / `python_cli_stop` / `python_cli_restart` para sesiones interactivas de Python (script o módulo). No ejecuta shell general.
- Robustez BD: borrado de proyectos en dos fases (items → proyecto) con FKs activas; sin parches de desactivar FKs.
- Docker: instala PyTorch estándar; si hay GPU disponible, se usará, si no, CPU.

## Requisitos

- Python 3.12
- `pip install -r requirements.txt`
- Conectividad inicial para extensiones DuckDB (`fts`, `vss`) y modelos locales (`voyageai/voyage-4-nano`, `Qwen/Qwen3-Reranker-0.6B`).

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

- En local el host por defecto es `127.0.0.1` (si no defines `APP_HOST`). En Docker se recomienda `APP_HOST=0.0.0.0` (ya incluido en `docker-compose.yml`). Botón “Restart MCP” reinicia el contenedor si `CONTAINER_NAME` está definido. Logs: `docker logs -f contextarium-tools`.

### Docker Compose

```bash
docker compose build
docker compose up
```

## Pruebas

```bash
python -m pytest
```

Valida RAG híbrido, BM25 (cuando FTS está disponible), contrato MCP y modelos de meta por tipo.

JSON Schema de items en tools MCP
- `store_item` y `update_item` exponen `typed` (oneOf por tipo; requerido en `store_item` para memory/bug/todo) y `meta` (oneOf opcional). Los clientes pueden construir payloads válidos sin JSONs largos obligatorios.

## TODO / próximo

- Mejorar soporte FTS/BM25 real en entornos donde la extensión falle (evitar fallback LIKE).
- Forzar refresco de tools en clientes MCP al inicio de sesión.
- (Opcional) Multi-corpus en la misma BD con filtrado por corpus en tools RAG.
