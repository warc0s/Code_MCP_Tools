from pathlib import Path


def test_bug_board_has_two_statuses_and_done_summary_in_template():
    js = Path('static/js/tabs/memory.js').read_text(encoding='utf-8')
    # bug board should filter to pending/resolved only
    assert 'getBoardStatusesForType(type)' in js
    assert "s.key === 'pending' || s.key === 'resolved'" in js
    # template/help should include done_summary mentions
    assert 'done_summary' in js
    # help text should not reference fixed_in_commit
    assert 'fixed_in_commit' not in js

