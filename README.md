# Auto_MCP_Tools

VERSION ACTUAL: V2.2

## Novedades principales de la V2.2

- Dualidad de modos `local` y `cloud` apuntalados por `config.yaml`, alternando entre modelos Qwen on-prem y endpoints OpenAI/DeepInfra sin tocar código.
- Ingesta reforzada que normaliza embeddings, persiste metadatos de ejecución y reconstruye índices DuckDB (HNSW + FTS) listos para consultas híbridas con MMR y reranker.
- Servidor MCP endurecido (FastAPI + uvicorn) con endpoints REST/JSON-RPC compatibles, validación estricta de payloads y trazabilidad mediante `toolCallId`.
- Guía operativa actualizada en `Extra/Guias/rag_mcp.md` con arquitectura, logging, despliegue Codex CLI y notas de conformidad MCP 2025.
- Nueva familia de opciones `1.x` en la CLI para reconstruir el RAG tanto desde un sitemap (1.1) como desde ficheros de URLs en la carpeta `txt/` (1.2), siempre reseteando la base de datos anterior.
- Al iniciar la CLI se muestra un resumen de la base de datos actual (ruta, número de documentos y algunas URLs de referencia) para recordar de “qué” son los documentos indexados.
- Configuración MCP ampliada en `config.yaml` (`mcp.tools`) para activar o desactivar tools específicas del servidor (por ejemplo, exponer solo `hybrid_search` y `chunks_by_url` en producción).

CLI para construir un RAG “enchufable” basado en DuckDB + MCP.

## Requisitos

- Python 3.12
- Dependencias en `requirements.txt` (`pip install -r requirements.txt`)
- Conectividad a internet la primera vez que DuckDB necesite descargar las extensiones `fts` y `vss`, y los modelos Qwen.

## Uso rápido

```bash
python app.py
```

Menú disponible:

1. **Crear/Sustituir RAG**  
   - 1.1) Desde sitemap: solicita la URL del sitemap, crawlea con Crawl4AI, hace chunking, genera embeddings y reconstruye `data/rag.duckdb`.  
   - 1.2) Desde fichero de URLs (`txt/`): lista los `.txt` en la carpeta `txt/`, cada uno con una URL por línea (se ignoran líneas vacías o que comiencen por `#`), crawlea esas páginas y reconstruye `data/rag.duckdb` con ellas.  
   - Cualquier opción 1.x elimina la base de datos actual y la recrea desde cero con los nuevos documentos.
2. **Ejecutar servidor MCP**: expone `/tools` y `/call` vía FastAPI/uvicorn. Requiere haber corrido antes alguna opción 1.x.

## Pruebas

```bash
python -m pytest
```

Valida uso de BM25, normalización + MMR de la búsqueda híbrida y el contrato de metadatos MCP.

## TODO / mejoras pendientes

- **FTS / BM25 real en DuckDB**: actualmente, si la tabla/índice `fts_main_chunks` no existe (por versión de DuckDB o incompatibilidad de la extensión `fts`), la búsqueda léxica cae automáticamente a un fallback basado en `LIKE` sobre `chunks.text`, con un scoring simple por número de coincidencias. Esto mantiene la funcionalidad, pero no es equivalente a un BM25 real.  
  - Pendiente: actualizar DuckDB y la extensión `fts` para que soporte correctamente `CREATE INDEX ... USING fts(text)`, asegurar la creación de `fts_main_chunks` en `utils.database.initialize_schema`, y validar que las consultas léxicas en `utils.retrieval._lexical_candidates` usan siempre `match_bm25`/`bm25` sin necesidad de fallback.
- **Refresco de tools MCP en clientes**: la configuración `mcp.tools` ya evita que ciertas tools (por ejemplo `dense_search` o `lexical_search`) se expongan desde el servidor, pero algunos clientes pueden seguir “recordando” tools antiguas si no vuelven a llamar a `tools/list`.  
  - Pendiente: documentar y/o implementar en los clientes de referencia un refresco explícito de tools al inicio de cada sesión para que solo se registren las tools efectivamente habilitadas en el servidor.
- **V2.5 – Múltiples corpus en la misma BD**: permitir almacenar y consultar varios “corpus” o frameworks (p. ej. `apps_sdk`, `gradio`, etc.) en la misma base `rag.duckdb`.  
  - Pendiente: añadir un campo `corpus`/`source` en la tabla `docs` (y, si aplica, en `chunks`), exponer en la CLI modos de ingesta incremental por corpus (además del modo actual de “sustituir”), y extender las tools (`hybrid_search`, `chunks_by_url`, etc.) con parámetros opcionales para filtrar por corpus y devolver el corpus de cada resultado.
- **V3.0 – Rediseño del servidor en fastmcp**: migrar el servidor MCP actual (FastAPI + wiring manual en `mcp/server.py` y `mcp/toolset.py`) a una implementación basada en `fastmcp` que declare tools de forma más declarativa y genere esquemas automáticamente.  
  - Pendiente: diseñar un wrapper que exponga el `Retriever` y las tools de RAG como funciones `fastmcp`, mantener compatibilidad con los esquemas actuales (`inputSchema`/`outputSchema`) y evaluar la migración progresiva antes de retirar el servidor MCP “manual”.
