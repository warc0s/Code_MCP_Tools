from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.config import MemoryDatabaseConfig
from utils.memory_db import bootstrap_memory_db
from utils.items import ItemService


def make_db(path: str = "data/test_memory_typed.sqlite3") -> MemoryDatabaseConfig:
    p = _Path(path)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
    return MemoryDatabaseConfig(path=p)


def test_store_bug_with_typed_only_succeeds():
    cfg = make_db()
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("p01")
    item = svc.store_item(
        project="p01",
        project_id=None,
        item_type="bug",
        title="B1",
        body_md="",
        tags=[],
        status="pending",
        meta={},
        typed={
            "severity": "low",
            "reproduction": "steps",
            "expected": "ok",
            "root_cause": "rc",
        },
    )
    assert item.type == "bug"
    assert item.typed.get("severity") == "low"


def test_update_todo_typed_partial():
    cfg = make_db("data/test_memory_typed2.sqlite3")
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("p01")
    item = svc.store_item(
        project="p01",
        project_id=None,
        item_type="todo",
        title="T1",
        body_md="",
        tags=[],
        status="pending",
        meta={},
        typed={"kind": "feature", "acceptance_criteria": ["a"], "priority": "p2"},
    )
    updated = svc.update_item(project="p01", project_id=None, item_id=item.id, fields={"typed": {"priority": "p1"}})
    assert updated.typed.get("priority") == "p1"
