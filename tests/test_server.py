"""
Pruebas del servidor FastAPI que expone el endpoint MCP JSON-RPC.
"""

from fastapi.testclient import TestClient

from mcp.server import build_app
from mcp.toolset import RAGToolset


class _StubRetriever:
    """Retriever mínimo para aislar las pruebas del servidor MCP."""

    def dense_search(self, query: str, top_k: int | None = None):
        return [{"query": query, "top_k": top_k, "kind": "dense"}]

    def lexical_search(self, query: str, top_k: int | None = None):
        return [{"query": query, "top_k": top_k, "kind": "lexical"}]

    def hybrid_search(self, query: str, top_k: int | None = None):
        return [{"query": query, "top_k": top_k, "kind": "hybrid"}]

    def chunks_for_url(self, url: str):
        return [{"url": url, "kind": "chunks"}]


def test_notifications_initialized_returns_202_without_body():
    """`notifications/initialized` debe devolver 202 Accepted sin cuerpo."""

    toolset = RAGToolset(retriever=_StubRetriever())
    app = build_app(toolset)
    client = TestClient(app)

    initialize_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    }
    response_initialize = client.post("/", json=initialize_payload)
    assert response_initialize.status_code == 200

    response_notification = client.post(
        "/",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert response_notification.status_code == 202
    assert response_notification.content == b""
