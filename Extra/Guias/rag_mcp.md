# RAG MCP

## Arquitectura rápida
- `config.yaml` centraliza rutas, chunking, retrieval y toggles (como MMR/reranker).
- `utils/` aloja módulos independientes: `crawling`, `chunking`, `embeddings`, `database`, `pipeline`, `retrieval`, `reranker`.
- La BBDD es DuckDB (`data/rag.duckdb`) con tablas `docs` y `chunks`, índices VSS (HNSW/cosine) y FTS (BM25).
- `mcp/` contiene `toolset` (esquemas JSON de cada tool) y `server` (FastAPI + uvicorn).
- `app.py` ofrece CLI: opción 1.x para reconstruir el RAG (desde sitemap o desde ficheros de URLs en `txt/`) y opción 2 para arrancar el servidor MCP.

## Modos de ejecución
- `config.yaml` expone `main.mode` con valores `local` o `cloud`.
- `local` usa los modelos HuggingFace configurados (`Qwen/Qwen3-Embedding-0.6B` y `Qwen/Qwen3-Reranker-0.6B`) descargándolos a `.cache/models/`.
- `cloud` usa el embedding OpenAI `text-embedding-3-small` vía API oficial (requiere `.env` con `openai_api_key=...`) y mantiene el reranker Qwen `8B` servido por DeepInfra (`DEEPINFRA_API_KEY=...` si activas reranking).
- La CLI muestra el modo y los modelos activos en cada iteración. Al iniciar el servidor se imprime un aviso si la BD DuckDB fue creada en otro modo, indicando los modelos almacenados vs. configurados y la dimensión registrada; puedes abortar o continuar bajo tu responsabilidad.
- Durante la ingesta se guardan en la tabla `metadata` los campos `runtime_mode`, `embedding_model_name`, `embedding_dim` y `reranker_model_name` para futuras verificaciones.

## Flujo de ingesta
1. CLI opción 1.1 pide un sitemap y ejecuta `utils.pipeline.rebuild_rag_from_sitemap`.
2. CLI opción 1.2 lista los ficheros `.txt` en la carpeta `txt/` (una URL por línea, se ignoran líneas vacías o que empiecen por `#`) y ejecuta `utils.pipeline.rebuild_rag_from_urls` con el fichero seleccionado.
3. En ambos casos se crawlera con Crawl4AI, se limpia/slugify y se deduplican páginas por fingerprint.
4. Chunking conserva jerarquía y bloques de código, con solapado configurable.
5. Se embebe con el modelo definido por el modo (`Qwen/Qwen3-Embedding-0.6B` en local o `text-embedding-3-small` en cloud), se normaliza y se guarda en DuckDB (`FLOAT[dim]`).
6. Índices resultantes: `hnsw(embedding, metric='cosine')` + `fts(text, stopwords='english')`.

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

## Notas operativas
- Se fuerza `DUCKDB_EXTENSION_DIRECTORY` a `.duckdb/extensions` para guardar FTS/VSS sin permisos root.
- Si faltan extensiones, DuckDB pedirá descargar una vez con red.
- Reranker activado por defecto (`enable_rerank: true`) usando Qwen `0.6B` en local o `8B` vía DeepInfra en cloud; desactívalo con `retrieval.enable_rerank`.
- Para operar en cloud define `openai_api_key` (o `OPENAI_API_KEY`) en `.env`; añade `DEEPINFRA_API_KEY` solo si mantienes el reranker remoto.
- El stack está fijado a CPU: no se usan `device_map`, flash attention ni aceleradores. Torch debe estar disponible en CPU (`pip install torch`).
- Todos los modelos de HuggingFace (embeddings y reranker) se cachean en `.cache/models` dentro del proyecto; puedes borrar esa carpeta para forzar una descarga limpia.
- `requirements.txt` incluye CPU libs y los clientes remotos (`torch`, `sentence-transformers`, FastAPI, `openai`, `requests`, etc.).
- El servidor MCP abre la base de datos en modo **solo lectura**, así que puedes lanzar scripts o consultas que necesiten leer `data/rag.duckdb` en paralelo (usa `duckdb.connect(path, read_only=True)`). La fase de `INSTALL` de extensiones se hace automáticamente con una conexión temporal de escritura antes de arrancar el servidor, por lo que no hace falta detenerlo para consultas auxiliares.

## Logging y depuración
- `mcp.server` arranca con nivel `INFO` por defecto (ajústalo con `LOG_LEVEL` si necesitas más o menos verbosidad) y registra cada tool solicitada, generando un `toolCallId` UUID cuando el cliente no envía uno y devolviendo `structuredContent` más un bloque `text` para maximizar compatibilidad con clientes MCP.
- La ruta REST `/call` y el método JSON-RPC `tools/call` registran los argumentos rechazados y mantienen el stacktrace cuando ocurre un fallo interno.
- `mcp.toolset` emite `DEBUG` por cada ejecución, informa cuántos resultados devolvió y deja constancia de validaciones rechazadas o errores.
- `utils.retrieval` ahora deja trazas `DEBUG`/`INFO` sobre consultas densas/léxicas/híbridas, faltas de resultados y problemas generando embeddings o contra DuckDB.
- Si prefieres menos ruido exporta `LOG_LEVEL=INFO` antes de lanzar `python app.py`.

## Cómo resetear la base de datos

- No es necesario borrar archivos manualmente.
- Cada vez que eliges una opción `1.x` en `python app.py`, se elimina la base de datos actual (`data/rag.duckdb`) y se crea una nueva desde cero.
- El nuevo índice se rellena únicamente con los documentos obtenidos del sitemap (1.1) o de las URLs del fichero seleccionado en `txt/` (1.2), sustituyendo por completo a los anteriores.

### Conformidad MCP (junio 2025)
- Desde 2025-06-18 la respuesta de `tools/call` coloca los resultados estructurados en `structuredContent` y deja `content` únicamente con un bloque `text` serializado con `json.dumps`. El identificador se expone en `_meta.toolCallId` para correlacionar trazas.
- `tools/list` publica también `outputSchema` y `title` por tool para facilitar validaciones de clientes MCP.
- El endpoint JSON-RPC acepta `logging/setLevel` y ajusta el nivel de la raíz de logging durante la sesión (útil para depurar sin reiniciar el servidor).

### Índices y compatibilidad DuckDB
- VSS (HNSW): se intenta habilitar `hnsw_enable_experimental_persistence`. Si tu DuckDB/VSS no lo soporta, se omite el índice y la búsqueda densa funcionará igualmente (un poco más lenta) ordenando por `<->`.
- FTS (BM25): se intenta crear el índice `USING fts(...)`. Si tu versión no reconoce el tipo `FTS`, se omite el índice y la búsqueda léxica cae a un fallback `LIKE` con ranking simple, para evitar errores. Para BM25 real, actualiza la extensión FTS.
