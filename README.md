# Auto_MCP_Tools

VERSION ACTUAL: V2.0

## Novedades principales de la V2

- Dualidad de modos `local` y `cloud` apuntalados por `config.yaml`, alternando entre modelos Qwen on-prem y endpoints OpenAI/DeepInfra sin tocar código.
- Ingesta reforzada que normaliza embeddings, persiste metadatos de ejecución y reconstruye índices DuckDB (HNSW + FTS) listos para consultas híbridas con MMR y reranker.
- Servidor MCP endurecido (FastAPI + uvicorn) con endpoints REST/JSON-RPC compatibles, validación estricta de payloads y trazabilidad mediante `toolCallId`.
- Guía operativa actualizada en `Extra/Guias/rag_mcp.md` con arquitectura, logging, despliegue Codex CLI y notas de conformidad MCP 2025.

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

1. **Crear/Sustituir nuevo RAG**: solicita sitemap, crawlea con Crawl4AI, chunking, genera embeddings Qwen y reconstruye `data/rag.duckdb`.
2. **Ejecutar servidor MCP**: expone `/tools` y `/call` vía FastAPI/uvicorn. Requiere haber corrido antes la opción 1.

## Pruebas

```bash
python -m pytest
```

Valida uso de BM25, normalización + MMR de la búsqueda híbrida y el contrato de metadatos MCP.
