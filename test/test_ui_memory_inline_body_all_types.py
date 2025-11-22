from pathlib import Path


def test_inline_editor_includes_body_for_all_types():
    js = Path('static/js/tabs/memory.js').read_text(encoding='utf-8')
    # Should include a single unconditional ie-body textarea in the inline editor template
    assert 'textarea class="input ie-body"' in js
    # Old conditional for doc/memory only should be removed
    assert "item.type === 'doc' || item.type === 'memory'" not in js

