from pathlib import Path


def test_status_auto_state_present():
    js = Path("static/js/tabs/rag.js").read_text(encoding="utf-8")
    assert "statusAuto" in Path("static/js/core/state.js").read_text(encoding="utf-8")
    assert "setStatusAutoRefresh" in js
