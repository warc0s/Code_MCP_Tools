"""
Toolset MCP para exponer búsquedas del RAG y tools de CLI.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from utils.cli_sessions import restart_session, send_input, start_session, stop_session

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

INTERACTIVE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "session_id": {"type": "string"},
        "output": {"type": "string"},
        "awaiting_input": {"type": "boolean"},
        "alive": {"type": "boolean"},
        "log_path": {"type": "string"},
        "status_hint": {"type": "string"},
        "next_step": {"type": "string"},
        "conda_env": {"type": "string"},
        "prompt_pattern": {"type": "string"},
    },
    "required": ["session_id", "output", "awaiting_input", "alive", "log_path"],
}


class RAGToolset:
    """
    Conjunto de tools MCP para búsquedas en el RAG y manejo de sesiones CLI.
    """

    def __init__(
        self,
        retriever,
        enabled_tools: Optional[Iterable[str]] = None,
        cli_logs_enabled: bool = True,
    ):
        self.retriever = retriever
        self.cli_logs_enabled = cli_logs_enabled
        all_tools: Dict[str, Dict[str, Any]] = {
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
            "cli_start": {
                "title": "Start interactive CLI session",
                "description": "Spawn an interactive CLI session (e.g., python app.py) and return initial output.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "conda_env": {"type": "string"},
                        "workdir": {"type": "string"},
                        "batch_queries": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "prompt_pattern": {"type": "string"},
                        "timeout": {"type": "number", "minimum": 0},
                        "env": {"type": "object"},
                    },
                    "required": ["command"],
                },
                "output_schema": INTERACTIVE_OUTPUT_SCHEMA,
            },
            "cli_send": {
                "title": "Send input to CLI session",
                "description": "Send input to an interactive CLI session and fetch the new output.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "text": {"type": "string"},
                        "timeout": {"type": "number", "minimum": 0},
                    },
                    "required": ["session_id", "text"],
                },
                "output_schema": INTERACTIVE_OUTPUT_SCHEMA,
            },
            "cli_stop": {
                "title": "Stop CLI session",
                "description": "Gracefully stop an interactive CLI session (SIGINT) and return final output.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "kill": {"type": "boolean"},
                    },
                    "required": ["session_id"],
                },
                "output_schema": INTERACTIVE_OUTPUT_SCHEMA,
            },
            "cli_restart": {
                "title": "Restart CLI session",
                "description": "Restart a previous CLI session using the original command and return the new output.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "timeout": {"type": "number", "minimum": 0},
                    },
                    "required": ["session_id"],
                },
                "output_schema": INTERACTIVE_OUTPUT_SCHEMA,
            },
        }
        if enabled_tools is not None:
            enabled_set = {name for name in enabled_tools if name in all_tools}
            disabled = {name for name in all_tools.keys() if name not in enabled_set}
            if not enabled_set:
                logger.warning(
                    "Configuración MCP sin tools válidas; se mantendrán todas las tools por defecto."
                )
                self._tools = all_tools
            else:
                if disabled:
                    logger.info("Tools MCP deshabilitadas por configuración: %s", ", ".join(sorted(disabled)))
                self._tools = {name: all_tools[name] for name in sorted(enabled_set)}
        else:
            self._tools = all_tools

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
            if expected_type == "number":
                if not isinstance(value, (int, float)):
                    raise ValueError(f"'{key}' debe ser numérico.")
                minimum = prop.get("minimum")
                if minimum is not None and float(value) < float(minimum):
                    raise ValueError(f"'{key}' debe ser >= {minimum}.")
            if expected_type == "boolean" and not isinstance(value, bool):
                raise ValueError(f"'{key}' debe ser booleano.")
            if expected_type == "object" and not isinstance(value, dict):
                raise ValueError(f"'{key}' debe ser un objeto.")
            if expected_type == "array":
                if not isinstance(value, list):
                    raise ValueError(f"'{key}' debe ser una lista.")
                item_type = prop.get("items", {}).get("type")
                if item_type:
                    for item in value:
                        if item_type == "string" and not isinstance(item, str):
                            raise ValueError(f"Cada elemento de '{key}' debe ser cadena.")

    def call(self, name: str, payload: Dict[str, Any]) -> Any:
        if name not in self._tools:
            logger.warning("Solicitud para tool desconocida: %s", name)
            raise ValueError(f"Tool desconocida: {name}")
        tool = self._tools[name]
        logger.debug("Ejecutando tool '%s' con payload=%s", name, payload)
        self._validate(tool["schema"], payload)
        try:
            if name == "dense_search":
                results = self.retriever.dense_search(payload["query"], top_k=payload.get("top_k"))
            elif name == "lexical_search":
                results = self.retriever.lexical_search(payload["query"], top_k=payload.get("top_k"))
            elif name == "hybrid_search":
                results = self.retriever.hybrid_search(payload["query"], top_k=payload.get("top_k"))
            elif name == "chunks_by_url":
                results = self.retriever.chunks_for_url(payload["url"])
            elif name == "cli_start":
                results = start_session(
                    command=payload["command"],
                    conda_env=payload.get("conda_env"),
                    workdir=payload.get("workdir"),
                    batch_queries=payload.get("batch_queries"),
                    prompt_pattern=payload.get("prompt_pattern"),
                    env=payload.get("env"),
                    timeout=float(payload.get("timeout", 1.5)),
                    log_enabled=self.cli_logs_enabled,
                )
            elif name == "cli_send":
                results = send_input(
                    session_id=payload["session_id"],
                    text=payload.get("text", ""),
                    timeout=float(payload.get("timeout", 1.5)),
                )
            elif name == "cli_stop":
                results = stop_session(
                    session_id=payload["session_id"],
                    kill=bool(payload.get("kill", False)),
                )
            elif name == "cli_restart":
                results = restart_session(
                    session_id=payload["session_id"],
                    timeout=float(payload.get("timeout", 1.5)),
                )
            else:
                raise ValueError(f"Tool no soportada: {name}")
            logger.info("Tool '%s' ejecutada correctamente.", name)
            return results
        except ValueError as exc:
            logger.warning("Error de validación en tool '%s': %s", name, exc)
            raise
        except Exception:
            logger.exception("Error inesperado ejecutando tool '%s'", name)
            raise


__all__ = [
    "RAGToolset",
    "SEARCH_OUTPUT_SCHEMA",
    "CHUNK_OUTPUT_SCHEMA",
    "INTERACTIVE_OUTPUT_SCHEMA",
]
