# Visual Summary Of MCP Tools

```mermaid
flowchart TD
    root([MCP Tools])
    rag{RAG}
    items{Items}

    root --> rag
    root --> items

    rag --> hybrid[hybrid_search<br/>Hybrid search with MMR/reranker]
    rag --> chunks[chunks_by_url<br/>All chunks for a URL]
    rag -.-|Disabled in config| dense[dense_search<br/>Pure vector search]
    rag -.-|Disabled in config| lexical[lexical_search<br/>BM25/FTS]

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
- `store_item`/`update_item`/`get_item`/`list_items`/`search_items`/`patch_doc`/`delete_item`: project-scoped item management (`project` or `project_id`). `typed` carries required per-type fields; `meta` is optional for extras. `patch_doc` edits docs by unified diff.

## Related UI Changes

- Dashboard -> Status: groups active tools by category and shows Memory counters for the active project.
- Dashboard -> Integrations: ready-to-copy snippets for Codex CLI, Claude Code, and GitHub Copilot (VS Code).
