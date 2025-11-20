# Resumen visual de tools MCP

```mermaid
flowchart TD
    root([Tools MCP])
    rag{RAG}
    cli{CLI}

    root --> rag
    root --> cli

    rag --> hybrid[hybrid_search<br/>Búsqueda híbrida con MMR/reranker]
    rag --> chunks[chunks_by_url<br/>Todos los chunks de una URL]
    rag -.-|Deshabilitado en config| dense[dense_search<br/>Vectorial pura]
    rag -.-|Deshabilitado en config| lexical[lexical_search<br/>BM25/FTS]

    cli --> start[cli_start<br/>Lanza sesión interactiva]
    cli --> send[cli_send<br/>Envía input y lee salida]
    cli --> stop[cli_stop<br/>Detiene sesión SIGINT/SIGKILL]
    cli --> restart[cli_restart<br/>Relanza con el comando original]
```

## Notas rápidas
- `hybrid_search`: mezcla denso+léxico, normaliza, aplica MMR y reranker si está activo.
- `chunks_by_url`: devuelve todos los chunks y metadatos de una URL.
- `dense_search` / `lexical_search`: están presentes pero deshabilitados en `config.yaml` (actívalos con `mcp.tools` o sets).
- `cli_start`/`cli_send`/`cli_stop`/`cli_restart`: control de CLIs de texto; soportan `conda_env`, `workdir`, `timeout` y devuelven `status_hint`/`next_step`. Logs en disco controlados por `mcp.cli_logs_enabled`.
