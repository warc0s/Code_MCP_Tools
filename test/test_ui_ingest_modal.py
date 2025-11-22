from pathlib import Path


def test_ingest_modal_present():
    html = Path("templates/index.html").read_text(encoding="utf-8")
    assert "id=\"ingest-modal\"" in html
    assert "showIngestSummaryModal" in html
    assert "gotoRagDocs" in html
