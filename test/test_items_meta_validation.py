from __future__ import annotations

import sys
from pathlib import Path as _Path
import pytest

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.config import MemoryDatabaseConfig
from utils.memory_db import bootstrap_memory_db
from utils.items import ItemService


def make_temp_db(path: str = "data/test_memory_meta.sqlite3") -> MemoryDatabaseConfig:
    p = _Path(path)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
    return MemoryDatabaseConfig(path=p)


def test_bug_meta_requires_minimum_fields():
    cfg = make_temp_db()
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("p1")
    with pytest.raises(Exception):
        svc.store_item(project="p1", project_id=None, item_type="bug", title="B1", body_md="", tags=[], status="pending", meta={})
    # Valid minimal bug meta
    rec = svc.store_item(
        project="p1", project_id=None, item_type="bug", title="B2", body_md="", tags=[], status="pending",
        meta={
            "severity": "low",
            "reproduction": "steps",
            "expected": "ok",
            "root_cause": "rc",
        }
    )
    assert rec.type == 'bug' and rec.meta.get('severity') == 'low'

