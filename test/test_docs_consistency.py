from __future__ import annotations

from pathlib import Path


def test_rag_guide_describes_current_server_flow():
    content = Path("Extra/Guias/rag_mcp.md").read_text(encoding="utf-8")

    assert "POST /ui/api/rebuild/sitemap" in content
    assert "POST /ui/api/rebuild/url-file" in content
    assert "option 1." not in content.lower()
    assert "option 2" not in content.lower()


def test_tools_summary_mentions_python_call_function():
    content = Path("Extra/Guias/tools_resumen.md").read_text(encoding="utf-8")

    assert "python_call_function" in content
