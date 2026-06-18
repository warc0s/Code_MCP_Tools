"""
MCP toolset exposing RAG search and project item tools.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, Iterable, Optional

from jsonschema import Draft202012Validator

from utils.items import ItemService
from utils.item_meta import (
    meta_json_schema,
    meta_json_schema_oneof,
    typed_json_schema,
    typed_json_schema_oneof,
)

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


class RAGToolset:
    """
    MCP tool collection for RAG searches and project item management.
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
    ):
        self.retriever = retriever
        self.item_service = item_service
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
                "description": "Hybrid dense+lexical search with score fusion, MMR and optional reranking. Recommended top_k: 6 (increase for recall). Do not call in parallel; run sequentially.",
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
                    "allOf": [
                        {
                            "if": {"properties": {"type": {"const": "memory"}}},
                            "then": {
                                "required": ["typed"],
                                "properties": {
                                    "typed": typed_json_schema("memory", required=True),
                                    "meta": meta_json_schema("memory"),
                                },
                            },
                        },
                        {
                            "if": {"properties": {"type": {"const": "doc"}}},
                            "then": {
                                "properties": {
                                    "typed": typed_json_schema("doc", required=True),
                                    "meta": meta_json_schema("doc"),
                                },
                            },
                        },
                        {
                            "if": {"properties": {"type": {"const": "bug"}}},
                            "then": {
                                "required": ["typed"],
                                "properties": {
                                    "typed": typed_json_schema("bug", required=True),
                                    "meta": meta_json_schema("bug"),
                                },
                            },
                        },
                        {
                            "if": {"properties": {"type": {"const": "todo"}}},
                            "then": {
                                "required": ["typed"],
                                "properties": {
                                    "typed": typed_json_schema("todo", required=True),
                                    "meta": meta_json_schema("todo"),
                                },
                            },
                        },
                    ],
                },
                "output_schema": ITEM_OUTPUT_SCHEMA,
            },
            "update_item": {
                "title": "Update item metadata",
                "description": "Update item fields (title, tags, status, meta, typed). MCP body diff edits for docs go through patch_doc.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "project_id": {"type": "string"},
                        "id": {"type": "string"},
                        "fields": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["memory", "doc", "bug", "todo"]},
                                "title": {"type": "string"},
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "status": {"type": "string"},
                                "meta": meta_json_schema_oneof(),
                                "typed": typed_json_schema_oneof(required=False),
                            },
                            "allOf": [
                                {
                                    "if": {"properties": {"type": {"const": "memory"}}},
                                    "then": {
                                        "properties": {
                                            "typed": typed_json_schema("memory", required=False),
                                            "meta": meta_json_schema("memory"),
                                        }
                                    },
                                },
                                {
                                    "if": {"properties": {"type": {"const": "doc"}}},
                                    "then": {
                                        "properties": {
                                            "typed": typed_json_schema("doc", required=False),
                                            "meta": meta_json_schema("doc"),
                                        }
                                    },
                                },
                                {
                                    "if": {"properties": {"type": {"const": "bug"}}},
                                    "then": {
                                        "properties": {
                                            "typed": typed_json_schema("bug", required=False),
                                            "meta": meta_json_schema("bug"),
                                        }
                                    },
                                },
                                {
                                    "if": {"properties": {"type": {"const": "todo"}}},
                                    "then": {
                                        "properties": {
                                            "typed": typed_json_schema("todo", required=False),
                                            "meta": meta_json_schema("todo"),
                                        }
                                    },
                                },
                            ],
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
            if disabled:
                logger.info("MCP tools disabled by configuration: %s", ", ".join(sorted(disabled)))
            self._tools = {name: all_tools[name] for name in sorted(enabled_set)}
        else:
            self._tools = all_tools
        self._all_tools = all_tools

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        return self._tools

    def set_enabled_tools(self, enabled_tools: Iterable[str]) -> None:
        enabled_set = {name for name in enabled_tools if name in self._all_tools}
        self._tools = {name: self._all_tools[name] for name in sorted(enabled_set)}
        disabled = set(self._all_tools.keys()) - enabled_set
        if disabled:
            logger.info("Disabled tools: %s", ", ".join(sorted(disabled)))
        logger.info("Enabled tools: %s", ", ".join(sorted(enabled_set)) or "(none)")

    def update_retriever(self, retriever) -> None:
        self.retriever = retriever

    def available_tools(self) -> list[str]:
        return sorted(self._all_tools.keys())

    def _item_to_dict(self, item) -> Dict[str, Any]:
        return asdict(item)

    def _validate(self, schema: Dict[str, Any], payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Tool arguments must be an object.")
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
        if errors:
            first = errors[0]
            path = ".".join(str(part) for part in first.path) or "(root)"
            raise ValueError(f"Invalid arguments at {path}: {first.message}.")

    def call(self, name: str, payload: Dict[str, Any]) -> Any:
        if name not in self._tools:
            logger.warning("Request for unknown tool: %s", name)
            raise ValueError(f"Unknown tool: {name}")
        tool = self._tools[name]
        if self.retriever is None and name in self._rag_tools:
            raise ValueError("RAG unavailable: database not initialized.")
        if name in self._item_tools and self.item_service is None:
            raise ValueError("Items service unavailable.")
        logger.debug("Executing tool '%s' with payload=%s", name, payload)
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
                raise ValueError(f"Unsupported tool: {name}")
            logger.info("Tool '%s' executed successfully.", name)
            return results
        except ValueError as exc:
            logger.warning("Validation error in tool '%s': %s", name, exc)
            raise
        except Exception:
            logger.exception("Unexpected error while executing tool '%s'", name)
            raise


__all__ = [
    "RAGToolset",
    "SEARCH_OUTPUT_SCHEMA",
    "CHUNK_OUTPUT_SCHEMA",
]
