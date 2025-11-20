# Code_MCP_Tools

VERSION ACTUAL: V2.5

CLI y servidor MCP orientados a **coding**: exponen tools declarativas para RAG sobre documentación y para orquestar CLIs interactivas (por ejemplo `python app.py`) desde agentes/LLMs sin colgarse.

## Novedades principales de la V2.5

- Dualidad de modos `local` y `cloud` apuntalados por `config.yaml`, alternando entre modelos Qwen on-prem y endpoints OpenAI/DeepInfra sin tocar código.
- Ingesta reforzada que normaliza embeddings, persiste metadatos de ejecución y reconstruye índices DuckDB (HNSW + FTS) listos para consultas híbridas con MMR y reranker.
- Servidor MCP basado en FastAPI + uvicorn (HTTP en `/mcp`) con tools declarativas pensadas para flujos de desarrollo: búsqueda en documentación técnica y control de CLIs de utilidades o tests.
- Tools MCP interactivas para controlar CLIs de texto (`cli_start`, `cli_send`, `cli_stop`, `cli_restart`) con soporte de `conda_env`, `workdir` y timeouts afinables (ver `Extra/Guias/cli_interactiva.md`).
- Guía operativa actualizada en `Extra/Guias/rag_mcp.md` con arquitectura, logging, despliegue Codex CLI y notas de conformidad MCP 2025 (servidor en `mcp_server/`).
- Nueva familia de opciones `1.x` en la CLI para reconstruir el RAG tanto desde un sitemap (1.1) como desde ficheros de URLs en la carpeta `txt/` (1.2), siempre reseteando la base de datos anterior.
- Al iniciar la CLI se muestra un resumen de la base de datos actual (ruta, número de documentos y algunas URLs de referencia) para recordar de “qué” son los documentos indexados.
- Configuración MCP ampliada en `config.yaml` (`mcp.tools`, `mcp.cli_logs_enabled`) para activar/desactivar tools específicas del servidor y el logging de sesiones de CLI.

CLI para construir un RAG “enchufable” basado en DuckDB + MCP y exponerlo como servidor de herramientas para agentes centrados en código.

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
2. **Ejecutar servidor MCP**: levanta un servidor FastAPI/uvicorn sobre HTTP (`http://127.0.0.1:PUERTO/mcp`) con las tools habilitadas en `config.yaml`. Requiere haber corrido antes alguna opción 1.x.

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
- **V3.0 – Múltiples corpus en la misma BD**: permitir almacenar y consultar varios “corpus” o frameworks (p. ej. `apps_sdk`, `gradio`, etc.) en la misma base `rag.duckdb`.  
  - Pendiente: añadir un campo `corpus`/`source` en la tabla `docs` (y, si aplica, en `chunks`), exponer en la CLI modos de ingesta incremental por corpus (además del modo actual de “sustituir”), y extender las tools (`hybrid_search`, `chunks_by_url`, etc.) con parámetros opcionales para filtrar por corpus y devolver el corpus de cada resultado.
