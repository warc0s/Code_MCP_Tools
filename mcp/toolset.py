"""
Toolset MCP para exponer búsquedas del RAG.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

SEARCH_RESULT_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "chunk_id": {"type": "string"},
        "doc_id": {"type": "string"},
        "url": {"type": "string"},
        "title": {"type": "string"},
        "section_path": {"type": "string"},
        "position": {"type": "integer"},
        "text": {"type": "string"},
        "score": {"type": "number"},
    },
    "required": ["chunk_id", "doc_id", "url", "text", "score"],
}

CHUNK_RESULT_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "chunk_id": {"type": "string"},
        "doc_id": {"type": "string"},
        "url": {"type": "string"},
        "title": {"type": "string"},
        "section_path": {"type": "string"},
        "position": {"type": "integer"},
        "text": {"type": "string"},
    },
    "required": ["chunk_id", "doc_id", "url", "text"],
}

SEARCH_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {"type": "array", "items": SEARCH_RESULT_ITEM_SCHEMA},
    },
    "required": ["results"],
}

CHUNK_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {"type": "array", "items": CHUNK_RESULT_ITEM_SCHEMA},
    },
    "required": ["results"],
}


class RAGToolset:
    def __init__(self, retriever, force_english_queries: bool = True):
        self.retriever = retriever
        self.force_english_queries = force_english_queries
        self._tools: Dict[str, Dict[str, Any]] = {
            "dense_search": {
                "title": "Dense search",
                "description": "Dense vector search using cosine similarity over the embedding index.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "minimum": 1},
                    },
                    "required": ["query"],
                },
                "output_schema": SEARCH_OUTPUT_SCHEMA,
            },
            "lexical_search": {
                "title": "Lexical search",
                "description": "Lexical BM25 search using DuckDB FTS.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "minimum": 1},
                    },
                    "required": ["query"],
                },
                "output_schema": SEARCH_OUTPUT_SCHEMA,
            },
            "hybrid_search": {
                "title": "Hybrid search",
                "description": "Hybrid dense+lexical search with score fusion, MMR and optional reranking.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "minimum": 1},
                    },
                    "required": ["query"],
                },
                "output_schema": SEARCH_OUTPUT_SCHEMA,
            },
            "chunks_by_url": {
                "title": "Chunks by URL",
                "description": "Retrieve every chunk extracted from a given documentation URL.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                    },
                    "required": ["url"],
                },
                "output_schema": CHUNK_OUTPUT_SCHEMA,
            },
        }

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        return self._tools

    def _validate(self, schema: Dict[str, Any], payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Los argumentos de la tool deben ser un objeto.")
        required = schema.get("required", [])
        for field in required:
            if field not in payload:
                raise ValueError(f"Falta el parámetro obligatorio '{field}'.")
        properties = schema.get("properties", {})
        for key, value in payload.items():
            prop = properties.get(key)
            if not prop:
                continue
            expected_type = prop.get("type")
            if expected_type == "string" and not isinstance(value, str):
                raise ValueError(f"'{key}' debe ser una cadena.")
            if expected_type == "integer":
                if not isinstance(value, int):
                    raise ValueError(f"'{key}' debe ser un entero.")
                minimum = prop.get("minimum")
                if minimum is not None and value < minimum:
                    raise ValueError(f"'{key}' debe ser >= {minimum}.")

    def call(self, name: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if name not in self._tools:
            logger.warning("Solicitud para tool desconocida: %s", name)
            raise ValueError(f"Tool desconocida: {name}")
        tool = self._tools[name]
        logger.debug("Ejecutando tool '%s' con payload=%s", name, payload)
        self._validate(tool["schema"], payload)
        results: Optional[List[Dict[str, Any]]] = None
        try:
            if name == "dense_search":
                results = self.retriever.dense_search(payload["query"], top_k=payload.get("top_k"))
            elif name == "lexical_search":
                results = self.retriever.lexical_search(payload["query"], top_k=payload.get("top_k"))
            elif name == "hybrid_search":
                results = self.retriever.hybrid_search(payload["query"], top_k=payload.get("top_k"))
            elif name == "chunks_by_url":
                results = self.retriever.chunks_for_url(payload["url"])
            else:
                raise ValueError(f"Tool no soportada: {name}")
            logger.info("Tool '%s' devolvió %s resultados.", name, len(results))
            return results
        except ValueError as exc:
            logger.warning("Error de validación en tool '%s': %s", name, exc)
            raise
        except Exception:
            logger.exception("Error inesperado ejecutando tool '%s'", name)
            raise
        raise ValueError(f"Tool no soportada: {name}")


__all__ = ["RAGToolset"]
