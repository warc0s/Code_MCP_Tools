from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mcp_server.server import build_app
from mcp_server.toolset import RAGToolset


def test_public_branding_uses_contextarium():
    files = [
        Path("README.md"),
        Path("templates/base.html"),
        Path("templates/index.html"),
        Path("templates/partials/footer.html"),
        Path("Extra/Guias/web_ui.md"),
    ]
    for path in files:
        content = path.read_text(encoding="utf-8")
        assert "Contextarium" in content, path
        assert " ".join(["Code", "MCP", "Server"]) not in content, path
        assert "_".join(["Code", "MCP", "Tools"]) not in content, path


def test_mcp_initialize_announces_contextarium():
    app = build_app(RAGToolset(retriever=None, enabled_tools=[], cli_logs_enabled=False), base_path="/mcp")
    response = TestClient(app).post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )

    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "Contextarium"
