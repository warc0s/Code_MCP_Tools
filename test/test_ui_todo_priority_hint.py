from pathlib import Path


def test_todo_priority_hint_present():
    js = Path('static/js/tabs/memory.js').read_text(encoding='utf-8')
    assert 'Priority levels: p0 (highest/urgent), p1 (high), p2 (normal)' in js

