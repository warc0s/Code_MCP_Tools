# Visual Summary Of MCP Tools

```mermaid
flowchart TD
    root([MCP Tools])
    rag{RAG}
    python_cli{Python CLI}
    items{Items}

    root --> rag
    root --> python_cli
    root --> items

    rag --> hybrid[hybrid_search<br/>Hybrid search with MMR/reranker]
    rag --> chunks[chunks_by_url<br/>All chunks for a URL]
    rag -.-|Disabled in config| dense[dense_search<br/>Pure vector search]
    rag -.-|Disabled in config| lexical[lexical_search<br/>BM25/FTS]

    python_cli --> start[python_cli_start<br/>Python script/module]
    python_cli --> send[python_cli_send<br/>Send input + read]
    python_cli --> stop[python_cli_stop<br/>SIGINT/SIGTERM/SIGKILL]
    python_cli --> restart[python_cli_restart<br/>Restart with same config]
    python_cli --> call[python_call_function<br/>Function call in subprocess]

    items --> store[store_item<br/>Create memory/doc/bug/todo]
    items --> update[update_item<br/>Update metadata]
    items --> get[get_item<br/>Retrieve an item by id]
    items --> list[list_items<br/>Filter by type/status/tags]
    items --> search[search_items<br/>Search text/meta]
    items --> patch[patch_doc<br/>Diff over doc body_md]
    items --> del[delete_item<br/>Delete an item]
```

## Quick Notes

- `hybrid_search`: combines dense+lexical search, normalizes scores, applies MMR, and reranks when enabled.
- `chunks_by_url`: returns every chunk and metadata for a URL.
- `dense_search` / `lexical_search`: present but disabled in `config.yaml`; enable them with `mcp.tools` or tool sets.
- Scope: the RAG index is global (not per project); Items tools operate per project.
- `python_cli_start`/`python_cli_send`/`python_cli_stop`/`python_cli_restart`: interactive Python sessions (script or module); accept `conda_env`, `workdir`, `timeout`, and return `status_hint`/`next_step`. Optional `max_bytes` limits the output delta per read (default 16000). They do not execute a general shell.
- `python_call_function`: non-interactive function calls to `utils.*`/`scripts.*` in a subprocess with structured `ok/result/stdout/stderr/error_*` output.
- `store_item`/`update_item`/`get_item`/`list_items`/`search_items`/`patch_doc`/`delete_item`: project-scoped item management (`project` or `project_id`). `typed` carries required per-type fields; `meta` is optional for extras. `patch_doc` edits docs by unified diff.

## Related UI Changes

- Dashboard -> Status: groups active tools by category and shows Memory counters for the active project.
- Dashboard -> Integrations: ready-to-copy snippets for Codex CLI, Claude Code, and GitHub Copilot (VS Code).
