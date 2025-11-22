from pathlib import Path


def test_show_button_and_modal_function_present():
    js = Path('static/js/tabs/memory.js').read_text(encoding='utf-8')
    assert 'openItemModal' in js
    assert 'Show' in js

