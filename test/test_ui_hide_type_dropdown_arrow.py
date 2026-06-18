from pathlib import Path


def test_css_hides_item_type_dropdown_arrow():
    css = Path('static/css/app.css').read_text(encoding='utf-8')
    assert '#item-type.input' in css
    assert 'appearance: none' in css
