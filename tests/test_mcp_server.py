from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from mcp.server import build_app
from mcp.toolset import RAGToolset


class DummyRetriever:
    def dense_search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        return [{"query": query, "mode": "dense", "top_k": top_k}]

    def lexical_search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        return [{"query": query, "mode": "lexical", "top_k": top_k}]

    def hybrid_search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        return [{"query": query, "mode": "hybrid", "top_k": top_k}]

    def chunks_for_url(self, url: str) -> List[Dict[str, Any]]:
        return [{"url": url, "mode": "chunks"}]


def _make_client() -> TestClient:
    toolset = RAGToolset(DummyRetriever(), force_english_queries=False)
    app = build_app(toolset)
    return TestClient(app)


def test_json_rpc_initialize():
    client = _make_client()
    response = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "pytest", "version": "1.0.0"}},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    result = payload["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "RAG MCP Server"


def test_json_rpc_list_tools():
    client = _make_client()
    response = client.post("/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert response.status_code == 200
    payload = response.json()
    tools = payload["result"]["tools"]
    tool_names = sorted(tool["name"] for tool in tools)
    assert tool_names == ["chunks_by_url", "dense_search", "hybrid_search", "lexical_search"]
    assert all("inputSchema" in tool for tool in tools)


def test_json_rpc_call_tool_dense_search():
    client = _make_client()
    response = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "dense_search", "arguments": {"query": "hola", "top_k": 3}},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    result = payload["result"]
    assert result["isError"] is False
    content = result["content"][0]
    assert content["type"] == "json"
    assert content["json"][0]["mode"] == "dense"


def test_json_rpc_notification_returns_no_content():
    client = _make_client()
    response = client.post("/", json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
    assert response.status_code == 204
