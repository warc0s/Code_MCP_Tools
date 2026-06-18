"""
Minimal MCP server exposed through FastAPI.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, Iterable, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from mcp_server.toolset import (
    RAGToolset,
)

logger = logging.getLogger(__name__)

JSON_RPC_VERSION = "2.0"
PROTOCOL_VERSION = "2025-06-18"
DEFAULT_HTTP_PATH = "/mcp"
Lifespan = Callable[[FastAPI], AsyncIterator[None]]


class ToolCall(BaseModel):
    tool: str = Field(..., description="Tool name to execute.")
    arguments: Dict[str, object] = Field(default_factory=dict, description="JSON arguments following the schema.")


@dataclass
class ServerInfo:
    host: str
    port: int
    url: str


def _normalize_base_path(path: str) -> str:
    cleaned = (path or "/").strip()
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    if cleaned != "/" and cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")
    return cleaned


def build_app(
    toolset: RAGToolset,
    base_path: str = DEFAULT_HTTP_PATH,
    lifespan: Optional[Lifespan] = None,
) -> FastAPI:
    app = FastAPI(title="Contextarium", version="0.1.0", lifespan=lifespan)
    base = _normalize_base_path(base_path)
    root_path = base if base != "/" else "/"

    def _json_rpc_result(request_id: Optional[object], result: Dict[str, object]) -> object:
        return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "result": result}

    def _json_rpc_error(request_id: Optional[object], code: int, message: str) -> object:
        payload = {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "error": {"code": code, "message": message}}
        logger.warning("JSON-RPC error code=%s message=%s", code, message)
        return payload

    def _structured_tool_result(tool_name: str, results: object) -> object:
        spec = toolset.list_tools().get(tool_name) or {}
        output_schema = spec.get("output_schema") or {}
        required = output_schema.get("required") or []
        properties = output_schema.get("properties") or {}
        if (
            isinstance(results, list)
            and "results" in required
            and isinstance(properties.get("results"), dict)
        ):
            return {"results": results}
        return results

    @app.get(f"{base}/health")
    async def healthcheck():
        return {"status": "ok"}

    @app.get(f"{base}/tools")
    async def list_tools():
        tools: list[Dict[str, object]] = []
        for name, spec in toolset.list_tools().items():
            tools.append(
                {
                    "name": name,
                    "description": spec["description"],
                    "schema": spec["schema"],
                    "output_schema": spec.get("output_schema"),
                }
            )
        return {"tools": tools}

    @app.post(f"{base}/call")
    async def call_tool(payload: ToolCall):
        logger.info("HTTP /call tool=%s", payload.tool)
        try:
            results = toolset.call(payload.tool, payload.arguments or {})
        except ValueError as exc:
            logger.warning("Tool '%s' rejected arguments: %s", payload.tool, exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Unexpected error in tool '%s'", payload.tool)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"tool": payload.tool, "results": results}

    @app.post(root_path)
    async def json_rpc_endpoint(request: Request):
        try:
            payload = await request.json()
        except Exception as exc:  # pragma: no cover - FastAPI handles parsing
            logger.debug("Failed to parse JSON-RPC: %s", exc)
            return _json_rpc_error(None, -32700, "Invalid JSON.")

        if not isinstance(payload, dict):
            return _json_rpc_error(None, -32600, "JSON-RPC request must be an object.")

        logger.debug("Received JSON-RPC payload: %s", payload)
        has_request_id = "id" in payload
        request_id = payload.get("id") if has_request_id else None
        method = payload.get("method")
        raw_params = payload.get("params", {})
        version = payload.get("jsonrpc")

        if version != JSON_RPC_VERSION:
            return _json_rpc_error(request_id, -32600, "Unsupported JSON-RPC version.")

        if method is None:
            return _json_rpc_error(request_id, -32600, "Missing method in JSON-RPC request.")

        if not has_request_id and not method.startswith("notifications/"):
            return Response(status_code=202)

        if raw_params is None:
            params: Dict[str, Any] = {}
        elif isinstance(raw_params, dict):
            params = raw_params
        else:
            if not has_request_id:
                return Response(status_code=202)
            return _json_rpc_error(request_id, -32602, "params must be a JSON object.")

        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": "Contextarium", "version": "0.1.0"},
                "capabilities": {"tools": {"listChanged": False}},
            }
            return _json_rpc_result(request_id, result)

        if method == "tools/list":
            tools: list[Dict[str, object]] = []
            for name, spec in toolset.list_tools().items():
                tool_entry: Dict[str, Any] = {
                    "name": name,
                    "description": spec["description"],
                    "inputSchema": spec["schema"],
                    "title": spec.get("title", name),
                }
                output_schema = spec.get("output_schema")
                if output_schema:
                    tool_entry["outputSchema"] = output_schema
                tools.append(tool_entry)
            return _json_rpc_result(request_id, {"tools": tools})

        if method == "logging/setLevel":
            level_name = (params or {}).get("level", "INFO")
            numeric_level = getattr(logging, str(level_name).upper(), logging.INFO)
            logging.getLogger().setLevel(numeric_level)
            logger.info("Logging level set to %s (%s)", level_name, numeric_level)
            return _json_rpc_result(request_id, {})

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            tool_call_id = params.get("toolCallId") or str(uuid.uuid4())
            if not tool_name:
                return _json_rpc_error(request_id, -32602, "Missing tool name in params.name.")
            if not isinstance(arguments, dict):
                return _json_rpc_error(request_id, -32602, "params.arguments must be a JSON object.")
            logger.info("JSON-RPC tools/call tool=%s toolCallId=%s", tool_name, tool_call_id)
            try:
                results = toolset.call(tool_name, arguments)
            except ValueError as exc:
                logger.warning("Tool '%s' rejected JSON-RPC arguments: %s", tool_name, exc)
                return _json_rpc_error(request_id, -32602, str(exc))
            except Exception as exc:  # pragma: no cover - logging for unexpected failures
                logger.exception("Unexpected error while executing tool %s", tool_name)
                return _json_rpc_error(request_id, -32000, f"Internal error: {exc}")
            logger.debug(
                "JSON-RPC tool=%s toolCallId=%s executed.",
                tool_name,
                tool_call_id,
            )
            structured = _structured_tool_result(tool_name, results)
            result_payload: Dict[str, object] = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(structured, ensure_ascii=False),
                    }
                ],
                "structuredContent": structured,
            }
            result_payload["_meta"] = {"toolCallId": tool_call_id}
            logger.debug("JSON-RPC response payload: %s", result_payload)
            return _json_rpc_result(request_id, result_payload)

        if method.startswith("notifications/"):
            return Response(status_code=202)

        if method == "ping":
            return _json_rpc_result(request_id, {"ok": True})

        return _json_rpc_error(request_id, -32601, f"Unsupported JSON-RPC method: {method}")

    if root_path != "/":
        @app.post("/")
        async def json_rpc_endpoint_root(request: Request):
            return await json_rpc_endpoint(request)

    return app


def build_server(
    retriever,
    enabled_tools: Optional[Iterable[str]] = None,
    name: str = "Contextarium",
) -> RAGToolset:
    del name  # kept only for signature compatibility
    return RAGToolset(
        retriever=retriever,
        enabled_tools=enabled_tools,
    )


def run_server(
    server: RAGToolset,
    host: str = "127.0.0.1",
    port: int = 8000,
    path: str = DEFAULT_HTTP_PATH,
) -> ServerInfo:
    import uvicorn

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if not isinstance(level, int):
        level = logging.INFO
        level_name = "INFO"
    if not logging.getLogger().handlers:
        logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    else:
        logging.getLogger().setLevel(level)

    base_path = _normalize_base_path(path)
    app = build_app(server, base_path=base_path)
    uvicorn_level = os.getenv("UVICORN_LOG_LEVEL", level_name.lower())
    config = uvicorn.Config(app=app, host=host, port=port, log_level=uvicorn_level)
    http_path = base_path if base_path != "/" else ""
    logger.info("Iniciando servidor MCP en %s:%s%s", host, port, http_path)
    instance = uvicorn.Server(config)
    instance.run()
    return ServerInfo(host=host, port=port, url=f"http://{host}:{port}{http_path}")


__all__ = ["build_server", "run_server", "ServerInfo", "DEFAULT_HTTP_PATH"]
