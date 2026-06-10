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
- `app.py` arranca un único servidor FastAPI/uvicorn que expone el endpoint MCP (`/mcp` por defecto) y un panel web en `/` para ingesta, estado y toggles de tools.

## Modos de ejecución
- `config.yaml` expone `main.mode` con valores `local` o `cloud`.
- `local` usa los modelos HuggingFace configurados (`voyageai/voyage-4-nano` para embeddings y `Qwen/Qwen3-Reranker-0.6B` para reranking) descargándolos a `.cache/models/`. Si hay GPU CUDA disponible en el entorno y Torch la detecta, se usará automáticamente; si no, caerá a CPU.
- `cloud` usa el embedding OpenAI `text-embedding-3-small` vía API oficial (requiere `.env` con `openai_api_key=...`) y mantiene el reranker Qwen `8B` servido por DeepInfra (`DEEPINFRA_API_KEY=...` si activas reranking).
- El panel muestra el modo y los modelos activos. Al iniciar el servidor se registra un aviso si la BD DuckDB fue creada en otro modo, indicando los modelos almacenados vs. configurados y la dimensión registrada.
- Durante la ingesta se guardan en la tabla `metadata` los campos `runtime_mode`, `embedding_model_name`, `embedding_dim` y `reranker_model_name` para futuras verificaciones.

### Rendimiento y cuellos de botella típicos
- Embeddings locales (por defecto `voyageai/voyage-4-nano`) en CPU pueden ser el mayor coste. Si no dispones de GPU, considera:
  - Aumentar `embeddings.batch_size` si hay memoria suficiente (p. ej., 128 en CPU, 256–512 en GPU).
  - Cambiar a `main.mode: cloud` para usar `text-embedding-3-small` (requiere `OPENAI_API_KEY`).
  - Bajar `embeddings.embedding_dim` a una dimensión Matryoshka soportada por `voyageai/voyage-4-nano` (`512` o `256`) y reconstruir el índice si necesitas menos almacenamiento/coste.
  - Usar un modelo local más ligero (p. ej., `sentence-transformers/all-MiniLM-L6-v2`, dim=384) si el dominio es EN y no necesitas multilingüe.
- Índices: HNSW/FTS se crean tras la inserción (no antes) para acelerar la carga.
- Crawler: ajusta `crawling.workers` (por defecto 1) y deja `cache_mode: enabled` para reutilizar descargas.
- `crawling.workers` se sanea en runtime entre 1 y 16 antes de llamar a Crawl4AI; valores `0`, negativos o excesivos no se propagan al dispatcher.

## Flujo de ingesta
1. El servidor expone rebuilds desde el panel web y la API: `POST /ui/api/rebuild/sitemap` para sitemap y `POST /ui/api/rebuild/url-file` para ficheros `.txt` en `txt/` (una URL por línea, se ignoran líneas vacías o que empiecen por `#`).
2. En ambos casos se crawlera con Crawl4AI, se limpia/slugify y se deduplican páginas por fingerprint.
3. Chunking conserva jerarquía y bloques de código, con solapado configurable (`chunking.respect_headings` y `chunking.preserve_code_blocks`).
4. Se embebe con el modelo definido por el modo (`voyageai/voyage-4-nano` en local o `text-embedding-3-small` en cloud), se normaliza y se guarda en una DuckDB temporal.
5. La BD temporal sustituye a la anterior mediante swap atómico; si el swap falla, se restaura la BD previa y se limpian temporales.
6. Índices resultantes: `hnsw(embedding, metric='cosine')` + `fts(text, stopwords='english')`.
   - Rendimiento: la creación de índices HNSW/FTS se difiere hasta después de la inserción masiva de `docs/chunks` para evitar mantenimiento incremental por fila. Esto reduce sensiblemente el tiempo total de rebuild a corpus medio/grande.

## Retrievers / Tools
- `dense_search`: solo vectorial (cosine).
- `lexical_search`: BM25 vía `fts_main_chunks` + `bm25(...)`.
- `hybrid_search`: normaliza dense/lexical, mezcla con `alpha`, aplica MMR (λ=0.5) + penalización URL (0.08) y opcional reranker Qwen.
- `hybrid_search` respeta `top_k` como límite final de salida; internamente usa más candidatos cuando hace falta para MMR/reranking.
- `chunks_by_url`: devuelve todos los chunks (metadatos completos) para reconstruir página.
- `python_cli_start`, `python_cli_send`, `python_cli_stop`, `python_cli_restart`: manejo de sesiones Python interactivas (ver `Extra/Guias/cli_interactiva.md`).
- `python_call_function`: ejecuta una función Python en un subproceso (no interactivo). Por defecto está deshabilitada en `config.yaml` y sólo permite módulos `utils.*`/`scripts.*`.
- `store_item`, `update_item`, `get_item`, `list_items`, `search_items`, `patch_doc`: tools para gestionar items por proyecto (memorias/docs/bugs/todos). `store_item`/`update_item` aceptan `typed` (campos obligatorios por tipo) y `meta` opcional; `patch_doc` edita docs por diff.
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
-       python_cli_start: true
-       python_cli_send: true
-       python_cli_stop: true
-       python_cli_restart: true
- ```
- 
- Usa `active_set` para elegir el conjunto expuesto; si no se especifica, se intentará usar `rag`. Si tampoco hay `tool_sets`, se exponen todas las tools por defecto.
- Un `tool_set` explícito con todas sus tools a `false` no cae al catálogo completo: el servidor no expone tools hasta que se habilite al menos una. Esto evita reabrir capacidades que el usuario había desactivado.
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
-     python_cli_start: true
-     python_cli_send: true
-     python_cli_stop: true
-     python_cli_restart: true
- ```
-
- En este modo, el servidor MCP registrará todas las tools marcadas como `true` en `mcp.tools` sin distinguir conjuntos.
- La UI valida nombres de tools y settings antes de escribir `config.yaml`; payloads inválidos se rechazan con 400 para no dejar la configuración en un estado no arrancable.

## Servidor MCP
- Servidor HTTP basado en FastAPI + uvicorn (ruta por defecto `/mcp`, configurable en el arranque) que expone las tools registradas en `mcp_server/toolset.py`.
- Implementa el protocolo MCP vía JSON‑RPC: maneja `initialize`, `tools/list`, `tools/call`, `logging/setLevel`, `ping` y notificaciones bajo la ruta configurada.
- Se arranca con `python app.py`; muestra la URL final (`http://127.0.0.1:PUERTO/mcp`) y mantiene la conexión DuckDB en modo solo lectura.
- Requiere que la BBDD exista previamente.

## Integraciones rápidas

### Codex CLI
1. Asegúrate de que el servidor escucha en `http://127.0.0.1:8000/mcp` (o tu URL).
2. Edita `~/.codex/config.toml` y pega:
   ```toml
   rmcp_client = true

   [mcp_servers.contextarium_local]
   url = "http://127.0.0.1:8000/mcp"
   startup_timeout_sec = 2
   tool_timeout_sec = 60
   ```
   Ajusta `url`/timeouts según tu entorno.

### Claude Code
```bash
claude mcp add --transport http contextarium http://127.0.0.1:8000/mcp
```
Verifica con `claude mcp list`. Puedes cambiar `contextarium` y `--scope` (`user|project|local`).

### GitHub Copilot (VS Code)
Crea `.vscode/mcp.json` en el repositorio con:
```json
{
  "servers": {
    "contextarium": {
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
  - El reranker no participa en la ingesta; sólo en búsqueda. No impacta el rebuild salvo por la carga inicial del modelo si ya está activo en el servidor.
- Para operar en cloud define `openai_api_key` (o `OPENAI_API_KEY`) en `.env`; añade `DEEPINFRA_API_KEY` solo si mantienes el reranker remoto.
- Embeddings cloud usa timeout y reintentos explícitos del cliente OpenAI: `OPENAI_TIMEOUT_SEC` (45s por defecto) y `OPENAI_MAX_RETRIES` (2 por defecto).
- GPU si está disponible: el proveedor de embeddings detecta CUDA y usa GPU de forma automática; si no, CPU. Asegúrate de instalar versiones emparejadas de Torch/TorchVision (por ejemplo, `torch==2.4.1` y `torchvision==0.19.1`).
- `voyageai/voyage-4-nano` se carga con `trust_remote_code=True` y `truncate_dim=1024` por defecto. Si configuras `embeddings.embedding_dim`, sólo se aceptan `2048`, `1024`, `512` o `256`, y el proveedor usa `encode_query`/`encode_document` para aplicar los prompts correctos de consulta/documento.
- Si aparece `ImportError: libnccl.so.*`, tu instalación de Torch requiere NCCL/CUDA. Opciones: instalar dependencias CUDA/NCCL del sistema, instalar la variante CPU de Torch o usar modo cloud para embedding.
- Si aparece `operator torchvision::nms does not exist`, instala/ajusta una versión de `torchvision` que empareje con tu `torch` (p. ej., `pip install torchvision==0.19.1`).
- Todos los modelos de HuggingFace (embeddings y reranker) se cachean en `.cache/models` dentro del proyecto; puedes borrar esa carpeta para forzar una descarga limpia.
- `requirements.txt` incluye CPU libs, `fastapi`, `uvicorn`, `pexpect` y los clientes remotos (`torch` CPU, `sentence-transformers`, `openai`, `requests`, etc.).
- El servidor MCP abre la base de datos en modo **solo lectura**, así que puedes lanzar scripts o consultas que necesiten leer `data/rag.duckdb` en paralelo (usa `duckdb.connect(path, read_only=True)`). La fase de `INSTALL` de extensiones se hace automáticamente con una conexión temporal de escritura antes de arrancar el servidor, por lo que no hace falta detenerlo para consultas auxiliares.

## Crawling: preset compatible (recomendado)

Para webs que bloquean headless o sirven HTML “vacío” (cookie walls, 403/robot checks), usa un preset más tolerante en `config.yaml`:
- `crawling.text_mode: false` (render completo)
- `crawling.enable_stealth: true` (si tu instalación lo soporta; si no, el crawler reintenta sin stealth)
- `crawling.cache_mode: disabled` (evita cachear páginas bloqueadas)
- `crawling.pruning_threshold: 0.2` y `crawling.pruning_min_word_threshold: 5` (menos poda)
- `crawling.min_markdown_chars: 120` (descarta páginas demasiado pequeñas)

Durante la ingesta se imprime un resumen de fallos por razón (p. ej. `blocked_or_empty`, `too_short_markdown`, `crawl_failed`) para poder iterar la configuración.

## Logging y depuración
- `mcp_server.server` inicializa FastAPI/uvicorn con `LOG_LEVEL` (INFO por defecto) y loguea cada tool invocada; el servidor serializa respuestas y schemas MCP.
- `utils.retrieval` deja trazas `DEBUG`/`INFO` sobre consultas densas/léxicas/híbridas, faltas de resultados y problemas generando embeddings o contra DuckDB.
- Si prefieres menos ruido exporta `LOG_LEVEL=INFO` antes de lanzar `python app.py`.

## Cómo resetear la base de datos

- No es necesario borrar archivos manualmente.
- Cada vez que eliges una opción `1.x` en `python app.py`, se construye el nuevo RAG (`docs`/`chunks`/`metadata`) en una DuckDB temporal y sólo se reemplaza la BD final si la ingesta termina correctamente. Si falla el crawler, embedding, inserción, índices o metadata, se conserva el índice anterior.
- El nuevo índice se rellena únicamente con los documentos obtenidos del sitemap (1.1) o de las URLs del fichero seleccionado en `txt/` (1.2), sustituyendo por completo a los anteriores pero dejando intactos proyectos/items.

### Conformidad MCP (junio 2025)
- El servidor FastAPI expone `tools/list` (incluido `outputSchema`/`title`) y `tools/call` sobre HTTP/JSON-RPC compatible con los clientes MCP streamable.
- Las respuestas incluyen `structuredContent` con el payload devuelto por cada tool y bloques `content` con un JSON de resultados.

### Índices y compatibilidad DuckDB
- VSS (HNSW): se intenta habilitar `hnsw_enable_experimental_persistence`. Si tu DuckDB/VSS no lo soporta, se omite el índice y la búsqueda densa funcionará igualmente (un poco más lenta) ordenando por `<->`.
- FTS (BM25): se intenta crear el índice `USING fts(...)`. Si tu versión no reconoce el tipo `FTS`, se omite el índice y la búsqueda léxica cae a un fallback `LIKE` con ranking simple, para evitar errores. Para BM25 real, actualiza la extensión FTS.
