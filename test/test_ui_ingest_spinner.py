from pathlib import Path


def test_rag_sitemap_button_passes_this_for_spinner():
    html = Path("templates/partials/rag.html").read_text(encoding="utf-8")
    # Ensure inline handler passes the button element so spinner can be applied
    assert 'onclick="rebuildSitemap(this)"' in html
    assert 'onclick="rebuildFile(this)"' in html
    # Rebuild progress widgets are present
    assert 'id="rebuild-progress-status"' in html
    assert 'id="rebuild-progress-bar"' in html
    assert 'id="rebuild-progress-meta"' in html


def test_setButtonLoading_uses_closest_button():
    js = Path("static/js/core/utils.js").read_text(encoding="utf-8")
    # Defensive behavior: closest('button') is used to find the button container
    assert "closest('button')" in js
