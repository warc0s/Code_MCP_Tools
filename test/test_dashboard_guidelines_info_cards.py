from pathlib import Path


def test_guidelines_info_cards_and_preview_present():
    html = Path('templates/partials/dashboard.html').read_text(encoding='utf-8')
    # Old builder should be gone
    assert 'data-guideline-toggle' not in html
    assert 'Guidelines Builder' not in html
    # Info cards present
    assert 'Guidelines: Info' in html
    assert 'Context7 MCP' in html
    assert 'Chrome DevTools (MCP)' in html
    assert 'Project name' in html
    assert 'RAG ingestion/index' in html
    assert 'Items & Memory' in html
    # Preview block present
    assert 'AGENTS.md' in html
    assert 'id="guidelines-content"' in html
    assert 'Copy to Clipboard' in html


def test_dashboard_status_pill_distinguishes_rag_readiness():
    js = Path('static/js/tabs/dashboard.js').read_text(encoding='utf-8')
    assert 'data.rag_ready' in js
    assert 'RAG Ready' in js
    assert 'RAG Needs Rebuild' in js
    assert 'RAG Not Ready' in js
