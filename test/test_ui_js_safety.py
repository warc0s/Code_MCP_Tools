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

