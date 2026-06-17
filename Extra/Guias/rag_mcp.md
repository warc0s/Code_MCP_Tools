# RAG MCP

Note: since this version, the app splits persistence across two DBs: DuckDB for RAG and SQLite for memory (`projects/items`). See `Extra/Guias/dbs_arquitectura.md`.

## Quick Architecture

- `config.yaml` centralizes paths, chunking, retrieval, and toggles such as MMR/reranker.
- `utils/` contains independent modules: `crawling`, `chunking`, `embeddings`, `database`, `pipeline`, `retrieval`, and `reranker`.
- RAG lives in DuckDB (`data/rag.duckdb`) and is recreated on rebuild (`docs`/`chunks` with VSS/FTS indexes). `projects/items` live in SQLite `data/memory.sqlite3`.

## Index Scope

- The RAG index is global (not partitioned by project). A rebuild replaces the complete global index with the ingested corpus.
- Memory (`projects/items`) is project-scoped. Project selection affects Memory, not RAG.
- `mcp_server/` defines the FastAPI-based MCP server and declarative tools in `server.py`.
- `app.py` starts one FastAPI/uvicorn server that exposes the MCP endpoint (`/mcp` by default) and a web panel at `/` for ingestion, status, and tool toggles.

## Execution Modes

- `config.yaml` exposes `main.mode` with `local` or `cloud` values.
- `local` uses the configured HuggingFace models (`voyageai/voyage-4-nano` for embeddings and `Qwen/Qwen3-Reranker-0.6B` for reranking), downloaded into `.cache/models/`. If CUDA GPU is available and Torch detects it, GPU is used automatically; otherwise it falls back to CPU.
- `cloud` uses the official OpenAI embedding `text-embedding-3-small` (requires `.env` with `openai_api_key=...`) and keeps Qwen `8B` reranking served by DeepInfra (`DEEPINFRA_API_KEY=...` if reranking is enabled).
- The panel shows the active mode and models. At server startup, a warning is logged if the DuckDB was created in another mode, including stored vs configured models and the recorded dimension.
- During ingestion, the `metadata` table stores `runtime_mode`, `embedding_model_name`, `embedding_dim`, and `reranker_model_name` for future checks.
- On startup, the server validates minimum `docs/chunks` columns and compares critical metadata (`runtime_mode`, `embedding_model_name`, and known `embedding_dim`) with `config.yaml`. If they do not match, it keeps the connection only for status/overview and does not expose a retriever until the index is rebuilt.

### Performance And Typical Bottlenecks

- Local embeddings (default `voyageai/voyage-4-nano`) on CPU can be the main cost. Without GPU, consider:
  - Increasing `embeddings.batch_size` if memory allows it (for example 128 on CPU, 256-512 on GPU).
  - Switching to `main.mode: cloud` to use `text-embedding-3-small` (requires `OPENAI_API_KEY`).
  - Lowering `embeddings.embedding_dim` to a Matryoshka dimension supported by `voyageai/voyage-4-nano` (`512` or `256`) and rebuilding the index if you need lower storage/cost.
  - Using a lighter local model (for example `sentence-transformers/all-MiniLM-L6-v2`, dim=384) if the domain is English and multilingual support is not needed.
- Indexes: HNSW/FTS are created after insertion (not before) to speed up loading.
- Crawler: tune `crawling.workers` (default 1) and keep `cache_mode: enabled` to reuse downloads.
- `crawling.workers` is sanitized at runtime between 1 and 16 before calling Crawl4AI; `0`, negative, or excessive values are not propagated to the dispatcher.

## Ingestion Flow

1. The server exposes rebuilds from the web panel and API: `POST /ui/api/rebuild/sitemap` for sitemaps and `POST /ui/api/rebuild/url-file` for `.txt` files in `txt/` (one URL per line; empty lines and lines starting with `#` are ignored).
2. Both paths crawl with Crawl4AI, clean/slugify, and deduplicate pages by normalized URL.
3. Chunks are identified by document/section/position to preserve repetitions across documents; identical fingerprints are not collapsed across different documents.
4. Chunking preserves hierarchy and code blocks, with configurable overlap (`chunking.respect_headings` and `chunking.preserve_code_blocks`).
5. Embeddings are generated with the model defined by the mode (`voyageai/voyage-4-nano` locally or `text-embedding-3-small` in cloud), normalized, and written to a temporary DuckDB.
6. The temporary DB replaces the previous one by atomic swap; if swap fails, the previous DB is restored and temporaries are cleaned.
7. Resulting indexes: `hnsw(embedding, metric='cosine')` + `fts(text, stopwords='english')`.
   - Performance: HNSW/FTS index creation is deferred until after bulk insertion of `docs/chunks` to avoid incremental per-row maintenance. This materially reduces total rebuild time for medium/large corpora.

## Retrievers / Tools

- `dense_search`: vector only (cosine).
- `lexical_search`: BM25 through `fts_main_chunks` + `bm25(...)`.
- `hybrid_search`: normalizes dense/lexical results, fuses with `alpha`, applies MMR (lambda=0.5) + URL penalty (0.08), and optional Qwen reranker.
- `hybrid_search` respects `top_k` as the final output limit; internally it uses more candidates when needed for MMR/reranking.
- If the reranker fails (network, cloud provider, local model), `hybrid_search` degrades to already-computed MMR results and logs a warning instead of breaking the full search. Cloud reranker errors redact tokens before serialization.
- `chunks_by_url`: returns all chunks (complete metadata) for reconstructing a page.
- `python_cli_start`, `python_cli_send`, `python_cli_stop`, `python_cli_restart`: interactive Python session management (see `Extra/Guias/cli_interactiva.md`).
- `python_call_function`: runs a Python function in a subprocess (non-interactive). It is disabled by default in `config.yaml` and only allows `utils.*`/`scripts.*` modules.
- `store_item`, `update_item`, `get_item`, `list_items`, `search_items`, `patch_doc`: tools to manage project-scoped items (memories/docs/bugs/todos). `store_item`/`update_item` accept `typed` (required per-type fields) and optional `meta`; `patch_doc` edits docs by diff.
- The MCP server publishes schemas (`outputSchema`) from the definition in `mcp_server/toolset.py`; extra validations (ASCII, minimums, etc.) are applied by `Retriever` when receiving the query.
- You can enable or disable tools exposed by the MCP server from `config.yaml` through sets (`mcp.tool_sets`), for example:

```yaml
mcp:
  active_set: rag
  tool_sets:
    rag:
      dense_search: false
      lexical_search: false
      hybrid_search: true
      chunks_by_url: true
    cli:
      python_cli_start: true
      python_cli_send: true
      python_cli_stop: true
      python_cli_restart: true
```

- Use `active_set` to choose the exposed set; if it is not specified, the server tries `rag`. If `tool_sets` is also absent, all tools are exposed by default.
- An explicit `tool_set` with every tool set to `false` does not fall back to the full catalog: the server exposes no tools until at least one is enabled. This avoids reopening capabilities the user disabled.
- To expose RAG tools and CLI tools at the same time, use a flat `mcp.tools` map instead of `tool_sets`, for example:

```yaml
mcp:
  tools:
    dense_search: false
    lexical_search: false
    hybrid_search: true
    chunks_by_url: true
    python_cli_start: true
    python_cli_send: true
    python_cli_stop: true
    python_cli_restart: true
```

- In this mode, the MCP server registers every tool marked `true` in `mcp.tools` without separating sets.
- The UI validates tool names and settings before writing `config.yaml`; invalid payloads are rejected with 400 so config is not left in an unstartable state.
- `mcp.tools` and `mcp.tool_sets` flags must be real YAML booleans (`true`/`false`), not strings such as `"false"`. If `active_set` is missing, `rag` is selected when available; otherwise the first set by sorted name is selected to avoid depending on file order.

## MCP Server

- HTTP server based on FastAPI + uvicorn (default route `/mcp`, configurable at startup) that exposes tools registered in `mcp_server/toolset.py`.
- Implements MCP through JSON-RPC: handles `initialize`, `tools/list`, `tools/call`, `logging/setLevel`, `ping`, and notifications under the configured route.
- Starts with `python app.py`; shows the final URL (`http://127.0.0.1:PORT/mcp`) and keeps the DuckDB connection in read-only mode.
- Requires the DB to exist beforehand.

## Quick Integrations

### Codex CLI

1. Make sure the server is listening at `http://127.0.0.1:8000/mcp` (or your URL).
2. Edit `~/.codex/config.toml` and paste:

   ```toml
   rmcp_client = true

   [mcp_servers.contextarium_local]
   url = "http://127.0.0.1:8000/mcp"
   startup_timeout_sec = 2
   tool_timeout_sec = 60
   ```

   Adjust `url`/timeouts for your environment.

### Claude Code

```bash
claude mcp add --transport http contextarium http://127.0.0.1:8000/mcp
```

Verify with `claude mcp list`. You can change `contextarium` and `--scope` (`user|project|local`).

### GitHub Copilot (VS Code)

Create `.vscode/mcp.json` in the repository with:

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

Open the Command Palette and run “MCP: List Servers” to verify it appears.

See also Dashboard -> Integrations for snippets with your current MCP URL and copy buttons.

## Operational Notes

- `DUCKDB_EXTENSION_DIRECTORY` is forced to `.duckdb/extensions` to store FTS/VSS without root permissions.
- If extensions are missing, DuckDB may need to download them once with network access.
- Reranker is enabled by default (`enable_rerank: true`) using Qwen `0.6B` locally or `8B` through DeepInfra in cloud; disable it with `retrieval.enable_rerank`.
  - The reranker is not part of ingestion; it only runs during search. It does not affect rebuilds except for the initial model load if the server already has it active.
- For cloud mode, define `openai_api_key` (or `OPENAI_API_KEY`) in `.env`; add `DEEPINFRA_API_KEY` only if you keep remote reranking enabled.
- If `.env` exists but cannot be read, startup logs a warning without dumping file contents.
- Cloud embeddings use explicit OpenAI client timeout and retries: `OPENAI_TIMEOUT_SEC` (45s by default) and `OPENAI_MAX_RETRIES` (2 by default).
- GPU when available: the embeddings provider detects CUDA and uses GPU automatically; otherwise CPU. Make sure to install paired Torch/TorchVision versions (for example `torch==2.4.1` and `torchvision==0.19.1`).
- `voyageai/voyage-4-nano` loads with `trust_remote_code=True` and `truncate_dim=1024` by default. If you configure `embeddings.embedding_dim`, only `2048`, `1024`, `512`, or `256` are accepted, and the provider uses `encode_query`/`encode_document` to apply the correct query/document prompts.
- If `ImportError: libnccl.so.*` appears, your Torch install requires NCCL/CUDA. Options: install system CUDA/NCCL dependencies, install the CPU Torch variant, or use cloud embedding mode.
- If `operator torchvision::nms does not exist` appears, install/adjust a `torchvision` version paired with your `torch` (for example `pip install torchvision==0.19.1`).
- All HuggingFace models (embeddings and reranker) are cached in `.cache/models` inside the project; delete that folder to force a clean download.
- `requirements.txt` includes CPU libs, `fastapi`, `uvicorn`, `pexpect`, and remote clients (`torch` CPU, `sentence-transformers`, `openai`, `requests`, etc.).
- The MCP server opens the database in **read-only** mode, so you can run scripts or queries that need to read `data/rag.duckdb` in parallel (use `duckdb.connect(path, read_only=True)`). The extension `INSTALL` phase is done automatically with a temporary write connection before server startup, so auxiliary reads do not require stopping the server.

## Crawling: Compatible Preset (Recommended)

For sites that block headless browsers or serve “empty” HTML (cookie walls, 403/robot checks), use a more tolerant preset in `config.yaml`:

- `crawling.text_mode: false` (full render)
- `crawling.enable_stealth: true` (if your installation supports it; otherwise the crawler retries without stealth)
- `crawling.cache_mode: disabled` (avoid caching blocked pages)
- `crawling.pruning_threshold: 0.2` and `crawling.pruning_min_word_threshold: 5` (less pruning)
- `crawling.min_markdown_chars: 120` (discard pages that are too small)

During ingestion, a failure summary by reason is printed (for example `blocked_or_empty`, `too_short_markdown`, `crawl_failed`) so configuration can be iterated.

## Logging And Debugging

- `mcp_server.server` initializes FastAPI/uvicorn with `LOG_LEVEL` (INFO by default) and logs every invoked tool; the server serializes MCP responses and schemas.
- `utils.retrieval` emits `DEBUG`/`INFO` traces for dense/lexical/hybrid queries, missing results, and embedding/DuckDB issues.
- If you prefer less noise, export `LOG_LEVEL=INFO` before launching `python app.py`.

## How To Reset The Database

- You do not need to delete files manually.
- Each time you choose a `1.x` option in `python app.py`, the new RAG (`docs`/`chunks`/`metadata`) is built in a temporary DuckDB and only replaces the final DB if ingestion completes successfully. If crawler, embedding, insertion, indexes, or metadata fail, the previous index is preserved.
- The new index is populated only with documents obtained from the sitemap (1.1) or URLs from the selected file in `txt/` (1.2), fully replacing previous RAG documents while leaving projects/items intact.

### MCP Compliance (June 2025)

- The FastAPI server exposes `tools/list` (including `outputSchema`/`title`) and `tools/call` over HTTP/JSON-RPC compatible with streamable MCP clients.
- Responses include `structuredContent` with the payload returned by each tool and `content` blocks containing a JSON result.

### DuckDB Indexes And Compatibility

- VSS (HNSW): attempts to enable `hnsw_enable_experimental_persistence`. If your DuckDB/VSS does not support it, the index is skipped and dense search still works (slower) by ordering with `<->`.
- FTS (BM25): attempts to create the index `USING fts(...)`. If your version does not recognize the `FTS` type, the index is skipped and lexical search falls back to simple ranked `LIKE` to avoid errors. Upgrade the FTS extension for real BM25.
