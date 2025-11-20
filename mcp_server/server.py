"""
Servidor MCP minimalista expuesto vía FastAPI.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from mcp_server.toolset import (
    CHUNK_OUTPUT_SCHEMA,
    INTERACTIVE_OUTPUT_SCHEMA,
    RAGToolset,
    SEARCH_OUTPUT_SCHEMA,
)

logger = logging.getLogger(__name__)

JSON_RPC_VERSION = "2.0"
PROTOCOL_VERSION = "2025-06-18"
DEFAULT_HTTP_PATH = "/mcp"


class ToolCall(BaseModel):
    tool: str = Field(..., description="Nombre de la tool a ejecutar.")
    arguments: Dict[str, object] = Field(default_factory=dict, description="Argumentos JSON que sigue el schema.")


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


def build_app(toolset: RAGToolset, base_path: str = DEFAULT_HTTP_PATH) -> FastAPI:
    app = FastAPI(title="Code_MCP", version="0.1.0")
    base = _normalize_base_path(base_path)
    root_path = base if base != "/" else "/"

    def _json_rpc_result(request_id: Optional[object], result: Dict[str, object]) -> object:
        if request_id is None:
            logger.debug("Petición sin id completada sin respuesta.")
            return Response(status_code=204)
        return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "result": result}

    def _json_rpc_error(request_id: Optional[object], code: int, message: str) -> object:
        payload = {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "error": {"code": code, "message": message}}
        logger.warning("JSON-RPC error code=%s message=%s", code, message)
        return payload

    @app.get(f"{base}/health")
    def healthcheck():
        return {"status": "ok"}

    @app.get(f"{base}/tools")
    def list_tools():
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
    def call_tool(payload: ToolCall):
        logger.info("HTTP /call tool=%s", payload.tool)
        try:
            results = toolset.call(payload.tool, payload.arguments or {})
        except ValueError as exc:
            logger.warning("Tool '%s' rechazó los argumentos: %s", payload.tool, exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Error inesperado en tool '%s'", payload.tool)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"tool": payload.tool, "results": results}

    @app.post(root_path)
    async def json_rpc_endpoint(request: Request):
        try:
            payload = await request.json()
        except Exception as exc:  # pragma: no cover - FastAPI maneja el parseo
            logger.debug("Fallo parseando JSON-RPC: %s", exc)
            return _json_rpc_error(None, -32700, "JSON inválido.")

        if not isinstance(payload, dict):
            return _json_rpc_error(None, -32600, "La petición JSON-RPC debe ser un objeto.")

        logger.debug("Payload JSON-RPC recibido: %s", payload)
        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params") or {}
        version = payload.get("jsonrpc")

        if version != JSON_RPC_VERSION:
            return _json_rpc_error(request_id, -32600, "Versión JSON-RPC no soportada.")

        if method is None:
            return _json_rpc_error(request_id, -32600, "Falta el método en la petición JSON-RPC.")

        if request_id is None and not method.startswith("notifications/"):
            return Response(status_code=202)

        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": "Code_MCP", "version": "0.1.0"},
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
            logger.info("Nivel de logging ajustado a %s (%s)", level_name, numeric_level)
            return _json_rpc_result(request_id, {})

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            tool_call_id = params.get("toolCallId") or str(uuid.uuid4())
            if not tool_name:
                return _json_rpc_error(request_id, -32602, "Falta el nombre de la tool en params.name.")
            logger.info("JSON-RPC tools/call tool=%s toolCallId=%s", tool_name, tool_call_id)
            try:
                results = toolset.call(tool_name, arguments)
            except ValueError as exc:
                logger.warning("Tool '%s' rechazó los argumentos JSON-RPC: %s", tool_name, exc)
                return _json_rpc_error(request_id, -32602, str(exc))
            except Exception as exc:  # pragma: no cover - logging para fallos inesperados
                logger.exception("Error inesperado ejecutando tool %s", tool_name)
                return _json_rpc_error(request_id, -32000, f"Error interno: {exc}")
            logger.debug(
                "JSON-RPC tool=%s toolCallId=%s ejecutada.",
                tool_name,
                tool_call_id,
            )
            result_payload: Dict[str, object] = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"results": results}, ensure_ascii=False),
                    }
                ],
                "structuredContent": {"results": results},
            }
            result_payload["_meta"] = {"toolCallId": tool_call_id}
            logger.debug("Payload de respuesta JSON-RPC: %s", result_payload)
            return _json_rpc_result(request_id, result_payload)

        if method.startswith("notifications/"):
            return Response(status_code=202)

        if method == "ping":
            return _json_rpc_result(request_id, {"ok": True})

        return _json_rpc_error(request_id, -32601, f"Método JSON-RPC no soportado: {method}")

    if root_path != "/":
        @app.post("/")
        async def json_rpc_endpoint_root(request: Request):
            return await json_rpc_endpoint(request)

    return app


def build_server(
    retriever,
    enabled_tools: Optional[Iterable[str]] = None,
    name: str = "Code_MCP",
    cli_logs_enabled: bool = True,
) -> RAGToolset:
    del name  # el nombre se mantiene solo para compatibilidad de firma
    return RAGToolset(
        retriever=retriever,
        enabled_tools=enabled_tools,
        cli_logs_enabled=cli_logs_enabled,
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
