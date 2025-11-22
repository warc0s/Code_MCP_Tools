"""
Toolset MCP para exponer búsquedas del RAG y tools de CLI.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional

from utils.cli_sessions import restart_session, send_input, start_session, stop_session
from utils.items import ItemService
from utils.item_meta import meta_json_schema_oneof, typed_json_schema_oneof

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

ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "project_id": {"type": "string"},
        "project_slug": {"type": "string"},
        "project_name": {"type": "string"},
        "type": {"type": "string"},
        "title": {"type": "string"},
        "body_md": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string"},
        "meta": {"type": "object"},
        "typed": {"type": "object"},
        "version": {"type": "integer"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
    "required": ["id", "project_id", "type", "title", "version"],
}

ITEM_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "item": ITEM_SCHEMA,
    },
    "required": ["item"],
}

ITEM_LIST_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": ITEM_SCHEMA},
    },
    "required": ["items"],
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
    _rag_tools = {"dense_search", "lexical_search", "hybrid_search", "chunks_by_url"}
    _item_tools = {
        "store_item",
        "update_item",
        "get_item",
        "list_items",
        "search_items",
        "patch_doc",
        "delete_item",
    }

    def __init__(
        self,
        retriever,
        item_service: Optional[ItemService] = None,
        enabled_tools: Optional[Iterable[str]] = None,
        cli_logs_enabled: bool = True,
    ):
        self.retriever = retriever
        self.item_service = item_service
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
            "store_item": {
                "title": "Store project item",
                "description": "Create a memory/doc/bug/todo item inside a project (uses project or project_id).",
                "schema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "project_id": {"type": "string"},
                        "type": {"type": "string", "enum": ["memory", "doc", "bug", "todo"]},
                        "title": {"type": "string"},
                        "body_md": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "status": {"type": "string"},
                        "meta": meta_json_schema_oneof(),
                        "typed": typed_json_schema_oneof(required=True),
                    },
                    "required": ["type", "title"],
                },
                "output_schema": ITEM_OUTPUT_SCHEMA,
            },
            "update_item": {
                "title": "Update item metadata",
                "description": "Update metadata (title, tags, status, meta) of an item. Body edits go through patch_doc.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "project_id": {"type": "string"},
                        "id": {"type": "string"},
                        "fields": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "status": {"type": "string"},
                                "meta": meta_json_schema_oneof(),
                                "typed": typed_json_schema_oneof(required=False),
                            },
                        },
                    },
                    "required": ["id", "fields"],
                },
                "output_schema": ITEM_OUTPUT_SCHEMA,
            },
            "get_item": {
                "title": "Get item",
                "description": "Retrieve a single item by id within a project.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "project_id": {"type": "string"},
                        "id": {"type": "string"},
                    },
                    "required": ["id"],
                },
                "output_schema": ITEM_OUTPUT_SCHEMA,
            },
            "list_items": {
                "title": "List items",
                "description": "List items in a project with optional filters (type, status, tags).",
                "schema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "project_id": {"type": "string"},
                        "type": {"type": "string", "enum": ["memory", "doc", "bug", "todo"]},
                        "status": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    },
                },
                "output_schema": ITEM_LIST_OUTPUT_SCHEMA,
            },
            "search_items": {
                "title": "Search items",
                "description": "Full-text search on items for a project, optionally filtered by type or tags.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "project_id": {"type": "string"},
                        "query": {"type": "string"},
                        "type": {"type": "string", "enum": ["memory", "doc", "bug", "todo"]},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    },
                    "required": ["query"],
                },
                "output_schema": ITEM_LIST_OUTPUT_SCHEMA,
            },
            "patch_doc": {
                "title": "Patch doc body",
                "description": "Apply a unified diff against a doc item body and bump version.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "project_id": {"type": "string"},
                        "id": {"type": "string"},
                        "unified_diff": {"type": "string"},
                        "expected_version": {"type": "integer", "minimum": 1},
                    },
                    "required": ["id", "unified_diff"],
                },
                "output_schema": ITEM_OUTPUT_SCHEMA,
            },
            "delete_item": {
                "title": "Delete item",
                "description": "Delete an item within a project.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "project_id": {"type": "string"},
                        "id": {"type": "string"},
                    },
                    "required": ["id"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"deleted": {"type": "boolean"}},
                    "required": ["deleted"],
                },
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
        self._all_tools = all_tools

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        return self._tools

    def set_enabled_tools(self, enabled_tools: Iterable[str]) -> None:
        enabled_set = {name for name in enabled_tools if name in self._all_tools}
        if not enabled_set:
            logger.warning("Petición de actualización sin tools válidas; se mantienen las actuales.")
            return
        self._tools = {name: self._all_tools[name] for name in sorted(enabled_set)}
        disabled = set(self._all_tools.keys()) - enabled_set
        if disabled:
            logger.info("Tools deshabilitadas: %s", ", ".join(sorted(disabled)))
        logger.info("Tools habilitadas: %s", ", ".join(sorted(enabled_set)))

    def update_retriever(self, retriever) -> None:
        self.retriever = retriever

    def available_tools(self) -> list[str]:
        return sorted(self._all_tools.keys())

    def _item_to_dict(self, item) -> Dict[str, Any]:
        return asdict(item)

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
            enum_values = prop.get("enum")
            if enum_values and value not in enum_values:
                raise ValueError(f"'{key}' debe ser uno de: {', '.join(enum_values)}.")

    def call(self, name: str, payload: Dict[str, Any]) -> Any:
        if name not in self._tools:
            logger.warning("Solicitud para tool desconocida: %s", name)
            raise ValueError(f"Tool desconocida: {name}")
        tool = self._tools[name]
        if self.retriever is None and name in self._rag_tools:
            raise ValueError("RAG no disponible: base de datos no inicializada.")
        if name in self._item_tools and self.item_service is None:
            raise ValueError("Servicio de items no disponible.")
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
            elif name == "store_item":
                item = self.item_service.store_item(
                    project=payload.get("project"),
                    project_id=payload.get("project_id"),
                    item_type=payload["type"],
                    title=payload["title"],
                    body_md=payload.get("body_md"),
                    tags=payload.get("tags"),
                    status=payload.get("status"),
                    meta=payload.get("meta"),
                    typed=payload.get("typed"),
                )
                results = {"item": self._item_to_dict(item)}
            elif name == "update_item":
                item = self.item_service.update_item(
                    project=payload.get("project"),
                    project_id=payload.get("project_id"),
                    item_id=payload["id"],
                    fields=payload.get("fields", {}),
                )
                results = {"item": self._item_to_dict(item)}
            elif name == "get_item":
                item = self.item_service.get_item(
                    project=payload.get("project"),
                    project_id=payload.get("project_id"),
                    item_id=payload["id"],
                )
                results = {"item": self._item_to_dict(item)}
            elif name == "list_items":
                items = self.item_service.list_items(
                    project=payload.get("project"),
                    project_id=payload.get("project_id"),
                    item_type=payload.get("type"),
                    status=payload.get("status"),
                    tags=payload.get("tags"),
                    limit=int(payload.get("limit", 50)),
                )
                results = {"items": [self._item_to_dict(item) for item in items]}
            elif name == "search_items":
                items = self.item_service.search_items(
                    project=payload.get("project"),
                    project_id=payload.get("project_id"),
                    query=payload["query"],
                    item_type=payload.get("type"),
                    tags=payload.get("tags"),
                    limit=int(payload.get("limit", 50)),
                )
                results = {"items": [self._item_to_dict(item) for item in items]}
            elif name == "patch_doc":
                item = self.item_service.patch_doc(
                    project=payload.get("project"),
                    project_id=payload.get("project_id"),
                    item_id=payload["id"],
                    unified_diff=payload["unified_diff"],
                    expected_version=payload.get("expected_version"),
                )
                results = {"item": self._item_to_dict(item)}
            elif name == "delete_item":
                self.item_service.delete_item(
                    project=payload.get("project"),
                    project_id=payload.get("project_id"),
                    item_id=payload["id"],
                )
                results = {"deleted": True}
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
