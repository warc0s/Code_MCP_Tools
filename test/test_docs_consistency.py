from __future__ import annotations

from pathlib import Path


def test_rag_guide_describes_current_server_flow():
    content = Path("Extra/Guias/rag_mcp.md").read_text(encoding="utf-8")

    assert "POST /ui/api/rebuild/sitemap" in content
    assert "POST /ui/api/rebuild/url-file" in content
