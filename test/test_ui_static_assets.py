from pathlib import Path


def test_base_template_includes_static_assets():
    tpl = Path('templates/base.html').read_text(encoding='utf-8')
    assert 'url_for' in tpl
    assert 'css/app.css' in tpl
    assert 'js/main.js' in tpl
    assert 'img/contextarium-logo.svg' in tpl
