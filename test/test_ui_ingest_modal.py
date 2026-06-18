from pathlib import Path


def test_ingest_modal_present():
    html = Path("templates/partials/ingest_modal.html").read_text(encoding="utf-8")
    assert 'id="ingest-modal"' in html
    js = Path("static/js/tabs/rag.js").read_text(encoding="utf-8")
    assert "showIngestSummaryModal" in js
    assert "gotoRagDocs" in js
