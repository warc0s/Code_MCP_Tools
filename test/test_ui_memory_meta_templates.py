from pathlib import Path


def test_update_meta_guidance_overwrites_meta_with_template():
    js = Path('static/js/tabs/memory.js').read_text(encoding='utf-8')
    assert 'function updateMetaGuidance()' in js
    assert 'metaEl.value = getMetaTemplate(' in js


def test_bug_template_includes_expected_field():
    js = Path('static/js/tabs/memory.js').read_text(encoding='utf-8')
    assert "expected: 'what should have happened instead'" in js


def test_todo_template_includes_dependencies_field():
    js = Path('static/js/tabs/memory.js').read_text(encoding='utf-8')
    assert 'dependencies: []' in js


def test_bug_template_includes_resolution_and_screenshots():
    js = Path('static/js/tabs/memory.js').read_text(encoding='utf-8')
    assert 'resolution_criteria' in js
    assert 'screenshots' in js
    assert 'related_files' in js

def test_todo_template_includes_related_files():
    js = Path('static/js/tabs/memory.js').read_text(encoding='utf-8')
    assert 'related_files' in js
