from pathlib import Path


def test_has_autorefresh_toggle():
    html = Path("templates/index.html").read_text(encoding="utf-8")
    assert "function setStatusAutoRefresh" in html
    assert "__statusAuto" in html
