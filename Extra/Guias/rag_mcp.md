# RAG MCP

## Arquitectura rápida
- `config.yaml` centraliza rutas, chunking, retrieval y toggles (como MMR/reranker).
- `utils/` aloja módulos independientes: `crawling`, `chunking`, `embeddings`, `database`, `pipeline`, `retrieval`, `reranker`.
- La BBDD es DuckDB (`data/rag.duckdb`) con tablas `docs` y `chunks`, índices VSS (HNSW/cosine) y FTS (BM25).
- `mcp/` contiene `toolset` (esquemas JSON de cada tool) y `server` (FastAPI + uvicorn).
- `app.py` ofrece CLI: (1) reconstruir RAG desde sitemap, (2) arrancar servidor MCP.

## Flujo de ingesta
1. CLI opción 1 pide sitemap y ejecuta `utils.pipeline.rebuild_rag_from_sitemap`.
2. Se crawlera con Crawl4AI, limpiar/slugify, deduplicar por fingerprint.
3. Chunking conserva jerarquía y bloques de código, con solapado configurable.
4. Se embebe con `Qwen/Qwen3-Embedding-0.6B`, normaliza y guarda en DuckDB (`FLOAT[dim]`).
5. Índices resultantes: `hnsw(embedding, metric='cosine')` + `fts(text, stopwords='english')`.

## Retrievers / Tools
- `dense_search`: solo vectorial (cosine).
- `lexical_search`: BM25 vía `fts_main_chunks` + `bm25(...)`.
- `hybrid_search`: normaliza dense/lexical, mezcla con `alpha`, aplica MMR (λ=0.5) + penalización URL (0.08) y opcional reranker Qwen.
- `chunks_by_url`: devuelve todos los chunks (metadatos completos) para reconstruir página.
- Cada tool valida payload vs JSON Schema y fuerza consultas ASCII si `policy.force_english_queries`.

## Servidor MCP
- API REST (`/health`, `/tools`, `/call`) servida con FastAPI.
- `POST /` expone el endpoint JSON-RPC 2.0 con `initialize`, `tools/list` y `tools/call` para la compatibilidad con MCP Streamable HTTP.
- Las notificaciones JSON-RPC (`notifications/initialized`) responden con `202 Accepted` y cuerpo vacío para mantener vivo al cliente Codex.
- Arranca con `uvicorn` desde CLI opción 2 (puerto configurable). Muestra URL y deja logs.
- Requiere que la BBDD exista previamente.

## Integración con Codex CLI
1. Arranca el servidor (`python app.py` → opción 2) para que escuche en `http://127.0.0.1:8000`.
2. Configura `~/.codex/config.toml` con:
   ```toml
   experimental_use_rmcp_client = true

   [mcp_servers.rag_local]
   url = "http://127.0.0.1:8000"
   startup_timeout_sec = 20
   tool_timeout_sec = 60
   ```
3. Reinicia Codex CLI y valida la conexión con `codex mcp list` o `codex mcp get rag_local`.
4. Ajusta `url`, `startup_timeout_sec` o `tool_timeout_sec` si cambias host/puerto o necesitas tolerancia extra.

## Pruebas
- `pytest` cubre que `lexical_search` usa `MATCH` + `bm25` y que híbrida normaliza/MMR/penaliza.
- También valida que las tools devuelven metadatos mínimos.
- Ejecuta `python -m pytest` tras cambios. `pytest` está en el entorno (añadido vía pip).

## Notas operativas
- Se fuerza `DUCKDB_EXTENSION_DIRECTORY` a `.duckdb/extensions` para guardar FTS/VSS sin permisos root.
- Si faltan extensiones, DuckDB pedirá descargar una vez con red.
- Reranker desactivado por defecto (`enable_rerank: false`) para evitar costes si no se necesita.
- El stack está fijado a CPU: no se usan `device_map`, flash attention ni aceleradores. Torch debe estar disponible en CPU (`pip install torch`).
- Todos los modelos de HuggingFace (embeddings y reranker) se cachean en `.cache/models` dentro del proyecto; puedes borrar esa carpeta para forzar una descarga limpia.
- `requirements.txt` cubre solo las dependencias necesarias en CPU (`torch`, `sentence-transformers`, FastAPI, etc.).
- El servidor MCP abre la base de datos en modo **solo lectura**, así que puedes lanzar scripts o pruebas que necesiten leer `data/rag.duckdb` en paralelo (usa `duckdb.connect(path, read_only=True)`). La fase de `INSTALL` de extensiones se hace automáticamente con una conexión temporal de escritura antes de arrancar el servidor, por lo que no hace falta detenerlo para consultas auxiliares.

## Logging y depuración
- `mcp.server` arranca con nivel `DEBUG` por defecto (puedes bajarlo con `LOG_LEVEL`) y registra cada tool solicitada, generando un `toolCallId` UUID cuando el cliente no envía uno y devolviendo tanto contenido `json` como `text` para maximizar compatibilidad con clientes MCP.
- La ruta REST `/call` y el método JSON-RPC `tools/call` registran los argumentos rechazados y mantienen el stacktrace cuando ocurre un fallo interno.
- `mcp.toolset` emite `DEBUG` por cada ejecución, informa cuántos resultados devolvió y deja constancia de validaciones rechazadas o errores.
- `utils.retrieval` ahora deja trazas `DEBUG`/`INFO` sobre consultas densas/léxicas/híbridas, faltas de resultados y problemas generando embeddings o contra DuckDB.
- Si prefieres menos ruido exporta `LOG_LEVEL=INFO` antes de lanzar `python app.py`.

### Índices y compatibilidad DuckDB
- VSS (HNSW): se intenta habilitar `hnsw_enable_experimental_persistence`. Si tu DuckDB/VSS no lo soporta, se omite el índice y la búsqueda densa funcionará igualmente (un poco más lenta) ordenando por `<->`.
- FTS (BM25): se intenta crear el índice `USING fts(...)`. Si tu versión no reconoce el tipo `FTS`, se omite el índice y la búsqueda léxica cae a un fallback `LIKE` con ranking simple, para evitar errores. Para BM25 real, actualiza la extensión FTS.
