from pathlib import Path


def test_rag_tab_has_status_autorefresh():
    js = Path("static/js/tabs/rag.js").read_text(encoding="utf-8")
    assert "setStatusAutoRefresh" in js
    assert "setInterval" in js
