from __future__ import annotations

import sys
from pathlib import Path as _Path
import pytest

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.config import MemoryDatabaseConfig
from utils.memory_db import bootstrap_memory_db
from utils.items import ItemService


def make_temp_db(path: str | _Path = "data/test_memory_meta.sqlite3") -> MemoryDatabaseConfig:
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
    svc.create_project("p01")
    with pytest.raises(Exception):
        svc.store_item(project="p01", project_id=None, item_type="bug", title="B1", body_md="", tags=[], status="pending", meta={})
    # Valid minimal bug meta
    rec = svc.store_item(
        project="p01", project_id=None, item_type="bug", title="B2", body_md="", tags=[], status="pending",
        meta={
            "severity": "low",
            "reproduction": "steps",
            "expected": "ok",
            "root_cause": "rc",
        }
    )
    assert rec.type == 'bug' and rec.meta.get('severity') == 'low'


def test_meta_must_be_an_object_for_store_and_update(tmp_path):
    cfg = make_temp_db(tmp_path / "memory.sqlite3")
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("meta-check")

    typed = {
        "kind": "feature",
        "acceptance_criteria": ["works"],
        "priority": "p1",
    }
    with pytest.raises(ValueError, match="meta must be an object"):
        svc.store_item(
            project="meta-check",
            project_id=None,
            item_type="todo",
            title="Bad meta",
            body_md="",
            tags=[],
            status="pending",
            meta="bad",
            typed=typed,
        )

    item = svc.store_item(
        project="meta-check",
        project_id=None,
        item_type="todo",
        title="Good meta",
        body_md="",
        tags=[],
        status="pending",
        meta={},
        typed=typed,
    )
    with pytest.raises(ValueError, match="meta must be an object"):
        svc.update_item(
            project="meta-check",
            project_id=None,
            item_id=item.id,
            fields={"meta": "bad"},
        )
