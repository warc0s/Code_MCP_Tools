from __future__ import annotations

import sys
from pathlib import Path as _Path

# Ensure repository root in sys.path for local imports
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from mcp_server.toolset import RAGToolset


def test_toolset_declares_output_schema():
    # Sin retriever ni item service: solo inspeccionamos el catálogo
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    tools = ts.list_tools()
    assert isinstance(tools, dict) and tools
    # Al menos una tool debe declarar output_schema (p. ej., hybrid_search)
    assert any("output_schema" in spec for spec in tools.values())


def test_hybrid_search_description_recommends_top_k():
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    tools = ts.list_tools()
    assert "hybrid_search" in tools
    desc = tools["hybrid_search"].get("description", "")
    assert "Recommended top_k" in desc
    assert "6" in desc
    assert "Do not call in parallel" in desc
