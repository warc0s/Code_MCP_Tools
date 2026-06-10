from __future__ import annotations

from pathlib import Path


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_ui_js_modules_do_not_use_innerhtml() -> None:
    js_files = [
        "static/js/core/toast.js",
        "static/js/tabs/rag.js",
        "static/js/tabs/dashboard.js",
        "static/js/tabs/config.js",
    ]
    for path in js_files:
        content = _read_text(path)
        assert "innerHTML" not in content, f"{path} still uses innerHTML"


def test_project_list_does_not_use_inline_onclick_in_js() -> None:
    content = _read_text("static/js/tabs/config.js")
    assert "onclick=" not in content


def test_memory_resolve_modal_escapes_prefilled_resolution_fields() -> None:
    content = _read_text("static/js/tabs/memory.js")
    assert "const doneSummary = escapeHtml(item.meta?.done_summary || '')" in content
    assert "const relatedFiles = escapeHtml((item.meta?.related_files || []).join(', '))" in content
    assert ".replace(/</g" not in content


def test_memory_modal_sanitizes_screenshot_links() -> None:
    content = _read_text("static/js/tabs/memory.js")
    assert "Array.isArray(m.screenshots)" in content
    assert "isValidUrl(url)" in content
    assert 'rel="noopener noreferrer"' in content


def test_theme_button_has_accessible_label() -> None:
    content = _read_text("templates/index.html")
    assert 'class="theme-toggle"' in content
    assert 'aria-label="Toggle theme"' in content


def test_inputs_have_focus_visible_style() -> None:
    content = _read_text("static/css/app.css")
    assert ".input:focus-visible" in content
    assert "outline:" in content
