from __future__ import annotations

import json

from fastapi.testclient import TestClient

from mcp_server.server import build_app
from mcp_server.toolset import RAGToolset


class FakeRetriever:
    def dense_search(self, query, top_k=None):
        return [
            {
                "chunk_id": "c1",
                "doc_id": "d1",
                "url": "https://example.com",
                "title": "Example",
                "section_path": "",
                "position": 1,
                "text": f"Result for {query}",
                "score": 1.0,
            }
        ]

    def lexical_search(self, query, top_k=None):
        return self.dense_search(query, top_k=top_k)

    def hybrid_search(self, query, top_k=None):
        return self.dense_search(query, top_k=top_k)

    def chunks_for_url(self, url):
        return [
            {
                "chunk_id": "c1",
                "doc_id": "d1",
                "url": url,
                "title": "Example",
                "section_path": "",
                "position": 1,
                "text": "Chunk",
            }
        ]


def _client() -> TestClient:
    toolset = RAGToolset(retriever=FakeRetriever(), enabled_tools=None)
    return TestClient(build_app(toolset, base_path="/mcp"))


def test_json_rpc_id_null_is_a_request_not_a_notification():
    client = _client()

    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": None, "method": "ping"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] is None
    assert payload["result"] == {"ok": True}


def test_json_rpc_rejects_non_object_params_without_500():
    client = _client()

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": "oops"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"]["code"] == -32602


def test_json_rpc_tools_call_matches_output_schema_shape():
    client = _client()

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {
                "name": "dense_search",
                "arguments": {"query": "alpha", "top_k": 1},
                "toolCallId": "tc-1",
            },
        },
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["structuredContent"]["results"][0]["chunk_id"] == "c1"
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert result["_meta"] == {"toolCallId": "tc-1"}

