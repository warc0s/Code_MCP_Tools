# RAG MCP

Nota: desde esta versión, la app separa la persistencia en dos BBDD: DuckDB para RAG y SQLite para memoria (`projects/items`). Consulta Extra/Guias/dbs_arquitectura.md.

## Arquitectura rápida
- `config.yaml` centraliza rutas, chunking, retrieval y toggles (como MMR/reranker).
- `utils/` aloja módulos independientes: `crawling`, `chunking`, `embeddings`, `database`, `pipeline`, `retrieval`, `reranker`.
- RAG vive en DuckDB (`data/rag.duckdb`) y se recrea en rebuild (`docs`/`chunks` con índices VSS/FTS). `projects/items` viven en SQLite `data/memory.sqlite3`.

## Ámbito del índice
- El índice RAG es global (no está particionado por proyecto). Un rebuild sustituye el índice global completo con el corpus ingerido.
- La memoria (proyectos/items) es por proyecto. La selección de proyecto impacta Memory, no el RAG.
- `mcp_server/` define el servidor MCP basado en FastAPI y las tools declarativas en `server.py`.
- `app.py` ahora arranca un único servidor FastAPI/uvicorn que expone el endpoint MCP (`/mcp` por defecto) y un panel web en `/` para ingesta, estado y toggles de tools sin usar la CLI.
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
- `cli_start`, `cli_send`, `cli_stop`, `cli_restart`: manejo de sesiones CLI interactivas (ver `Extra/Guias/cli_interactiva.md`).
- `store_item`, `update_item`, `get_item`, `list_items`, `search_items`, `patch_doc`: tools para gestionar items por proyecto (memorias/docs/bugs/todos) con edición de docs por diff.
- El servidor MCP publica los esquemas (`outputSchema`) a partir de la definición en `mcp_server/toolset.py`; las validaciones adicionales (ASCII, mínimos, etc.) las aplica `Retriever` al recibir la consulta.
- Puedes activar o desactivar tools expuestas por el servidor MCP desde `config.yaml` mediante conjuntos (`mcp.tool_sets`), por ejemplo:
- 
- ```yaml
- mcp:
-   active_set: rag
-   tool_sets:
-     rag:
-       dense_search: false
-       lexical_search: false
-       hybrid_search: true
-       chunks_by_url: true
-     cli:
-       cli_start: true
-       cli_send: true
-       cli_stop: true
-       cli_restart: true
- ```
- 
- Usa `active_set` para elegir el conjunto expuesto; si no se especifica, se intentará usar `rag`. Si tampoco hay `tool_sets`, se exponen todas las tools por defecto.
-
- Si quieres exponer a la vez las tools de RAG **y** las de CLI, puedes usar un mapa plano en `mcp.tools` en lugar de `tool_sets`, por ejemplo:
-
- ```yaml
- mcp:
-   tools:
-     dense_search: false
-     lexical_search: false
-     hybrid_search: true
-     chunks_by_url: true
-     cli_start: true
-     cli_send: true
-     cli_stop: true
-     cli_restart: true
- ```
-
- En este modo, el servidor MCP registrará todas las tools marcadas como `true` en `mcp.tools` sin distinguir conjuntos.

## Servidor MCP
- Servidor HTTP basado en FastAPI + uvicorn (ruta por defecto `/mcp`, configurable en el arranque) que expone las tools registradas en `mcp_server/toolset.py`.
- Implementa el protocolo MCP vía JSON‑RPC: maneja `initialize`, `tools/list`, `tools/call`, `logging/setLevel`, `ping` y notificaciones bajo la ruta configurada.
- Se arranca desde la opción 2 del CLI; muestra la URL final (`http://127.0.0.1:PUERTO/mcp`) y mantiene la conexión DuckDB en modo solo lectura.
- Requiere que la BBDD exista previamente.

## Integraciones rápidas

### Codex CLI
1. Asegúrate de que el servidor escucha en `http://127.0.0.1:8000/mcp` (o tu URL).
2. Edita `~/.codex/config.toml` y pega:
   ```toml
   rmcp_client = true

   [mcp_servers.codeMCP_local]
   url = "http://127.0.0.1:8000/mcp"
   startup_timeout_sec = 2
   tool_timeout_sec = 60
   ```
   Ajusta `url`/timeouts según tu entorno.

### Claude Code
```bash
claude mcp add --transport http code-mcp http://127.0.0.1:8000/mcp
```
Verifica con `claude mcp list`. Puedes cambiar `code-mcp` y `--scope` (`user|project|local`).

### GitHub Copilot (VS Code)
Crea `.vscode/mcp.json` en el repositorio con:
```json
{
  "servers": {
    "code-mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```
Abre la paleta de comandos y ejecuta “MCP: List Servers” para verificar que aparece.

Consulta también Dashboard → Integrations para snippets con tu MCP URL actual y botones de copia.

## Notas operativas
- Se fuerza `DUCKDB_EXTENSION_DIRECTORY` a `.duckdb/extensions` para guardar FTS/VSS sin permisos root.
- Si faltan extensiones, DuckDB pedirá descargar una vez con red.
- Reranker activado por defecto (`enable_rerank: true`) usando Qwen `0.6B` en local o `8B` vía DeepInfra en cloud; desactívalo con `retrieval.enable_rerank`.
- Para operar en cloud define `openai_api_key` (o `OPENAI_API_KEY`) en `.env`; añade `DEEPINFRA_API_KEY` solo si mantienes el reranker remoto.
- El stack está fijado a CPU: no se usan `device_map`, flash attention ni aceleradores. Torch debe estar disponible en CPU (`pip install torch`).
- Todos los modelos de HuggingFace (embeddings y reranker) se cachean en `.cache/models` dentro del proyecto; puedes borrar esa carpeta para forzar una descarga limpia.
- `requirements.txt` incluye CPU libs, `fastapi`, `uvicorn`, `pexpect` y los clientes remotos (`torch`, `sentence-transformers`, `openai`, `requests`, etc.).
- El servidor MCP abre la base de datos en modo **solo lectura**, así que puedes lanzar scripts o consultas que necesiten leer `data/rag.duckdb` en paralelo (usa `duckdb.connect(path, read_only=True)`). La fase de `INSTALL` de extensiones se hace automáticamente con una conexión temporal de escritura antes de arrancar el servidor, por lo que no hace falta detenerlo para consultas auxiliares.

## Logging y depuración
- `mcp_server.server` inicializa FastAPI/uvicorn con `LOG_LEVEL` (INFO por defecto) y loguea cada tool invocada; el servidor serializa respuestas y schemas MCP.
- `utils.retrieval` deja trazas `DEBUG`/`INFO` sobre consultas densas/léxicas/híbridas, faltas de resultados y problemas generando embeddings o contra DuckDB.
- Si prefieres menos ruido exporta `LOG_LEVEL=INFO` antes de lanzar `python app.py`.

## Cómo resetear la base de datos

- No es necesario borrar archivos manualmente.
- Cada vez que eliges una opción `1.x` en `python app.py`, se recrea el esquema RAG (`docs`/`chunks`/`metadata`) en la BD pero se preservan las tablas de `projects/items`.
- El nuevo índice se rellena únicamente con los documentos obtenidos del sitemap (1.1) o de las URLs del fichero seleccionado en `txt/` (1.2), sustituyendo por completo a los anteriores pero dejando intactos proyectos/items.

### Conformidad MCP (junio 2025)
- El servidor FastAPI expone `tools/list` (incluido `outputSchema`/`title`) y `tools/call` sobre HTTP/JSON-RPC compatible con los clientes MCP streamable.
- Las respuestas incluyen `structuredContent` con el payload devuelto por cada tool y bloques `content` con un JSON de resultados.

### Índices y compatibilidad DuckDB
- VSS (HNSW): se intenta habilitar `hnsw_enable_experimental_persistence`. Si tu DuckDB/VSS no lo soporta, se omite el índice y la búsqueda densa funcionará igualmente (un poco más lenta) ordenando por `<->`.
- FTS (BM25): se intenta crear el índice `USING fts(...)`. Si tu versión no reconoce el tipo `FTS`, se omite el índice y la búsqueda léxica cae a un fallback `LIKE` con ranking simple, para evitar errores. Para BM25 real, actualiza la extensión FTS.
