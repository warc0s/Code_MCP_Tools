"""
Servidor MCP basado en fastmcp para exponer búsquedas del RAG.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

SEARCH_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
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
            },
        },
    },
    "required": ["results"],
}

CHUNK_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
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
            },
        },
    },
    "required": ["results"],
}

DEFAULT_HTTP_PATH = "/mcp"


@dataclass
class ServerInfo:
    host: str
    port: int
    url: str


def _register_tools(
    server: FastMCP,
    retriever,
    enabled_tools: Optional[Set[str]] = None,
) -> None:
    def _is_enabled(name: str) -> bool:
        return enabled_tools is None or name in enabled_tools

    def _wrap(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"results": results}

    if enabled_tools is not None:
        disabled = {"dense_search", "lexical_search", "hybrid_search", "chunks_by_url"} - enabled_tools
        if disabled:
            logger.info("Tools MCP deshabilitadas por configuración: %s", ", ".join(sorted(disabled)))

    if _is_enabled("dense_search"):
        @server.tool(
            name="dense_search",
            title="Dense search",
            description="Dense vector search using cosine similarity over the embedding index.",
            output_schema=SEARCH_OUTPUT_SCHEMA,
        )
        def dense_search(query: str, top_k: Optional[int] = None) -> Dict[str, Any]:
            logger.info("Tool dense_search invocada top_k=%s", top_k)
            return _wrap(retriever.dense_search(query, top_k=top_k))

    if _is_enabled("lexical_search"):
        @server.tool(
            name="lexical_search",
            title="Lexical search",
            description="Lexical BM25 search using DuckDB FTS.",
            output_schema=SEARCH_OUTPUT_SCHEMA,
        )
        def lexical_search(query: str, top_k: Optional[int] = None) -> Dict[str, Any]:
            logger.info("Tool lexical_search invocada top_k=%s", top_k)
            return _wrap(retriever.lexical_search(query, top_k=top_k))

    if _is_enabled("hybrid_search"):
        @server.tool(
            name="hybrid_search",
            title="Hybrid search",
            description="Hybrid dense+lexical search with score fusion, MMR and optional reranking.",
            output_schema=SEARCH_OUTPUT_SCHEMA,
        )
        def hybrid_search(query: str, top_k: Optional[int] = None) -> Dict[str, Any]:
            logger.info("Tool hybrid_search invocada top_k=%s", top_k)
            return _wrap(retriever.hybrid_search(query, top_k=top_k))

    if _is_enabled("chunks_by_url"):
        @server.tool(
            name="chunks_by_url",
            title="Chunks by URL",
            description="Retrieve every chunk extracted from a given documentation URL.",
            output_schema=CHUNK_OUTPUT_SCHEMA,
        )
        def chunks_by_url(url: str) -> Dict[str, Any]:
            logger.info("Tool chunks_by_url invocada url=%s", url)
            return _wrap(retriever.chunks_for_url(url))


def build_server(
    retriever,
    enabled_tools: Optional[Iterable[str]] = None,
    name: str = "RAG MCP Server",
) -> FastMCP:
    enabled_set: Optional[Set[str]] = None
    if enabled_tools:
        enabled_set = {tool for tool in enabled_tools}
        if not enabled_set:
            enabled_set = None
    server = FastMCP(name)
    _register_tools(server, retriever, enabled_set)
    return server


def run_server(
    server: FastMCP,
    host: str = "127.0.0.1",
    port: int = 8000,
    path: str = DEFAULT_HTTP_PATH,
) -> ServerInfo:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if not isinstance(level, int):
        level = logging.INFO
    if not logging.getLogger().handlers:
        logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    else:
        logging.getLogger().setLevel(level)

    logger.info("Iniciando servidor fastmcp en %s:%s (path=%s)", host, port, path)
    server.run(transport="http", host=host, port=port, path=path)
    return ServerInfo(host=host, port=port, url=f"http://{host}:{port}{path}")


__all__ = ["build_server", "run_server", "ServerInfo", "DEFAULT_HTTP_PATH"]
