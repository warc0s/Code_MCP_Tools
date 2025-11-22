from __future__ import annotations

import sys
from pathlib import Path as _Path

# Ensure repository root in sys.path for local imports
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.config import MemoryDatabaseConfig
from utils.memory_db import bootstrap_memory_db
from utils.items import ItemService


def make_temp_db(path: str = "data/test_memory_todo_bug.sqlite3") -> MemoryDatabaseConfig:
    p = _Path(path)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
    return MemoryDatabaseConfig(path=p)


def test_replace_body_works_for_todo_and_bug():
    cfg = make_temp_db()
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)

    proj = svc.create_project("proj-x", name="Proj X")
    assert proj["slug"] == "proj-x"

    todo = svc.store_item(
        project="proj-x",
        project_id=None,
        item_type="todo",
        title="Todo A",
        body_md="alpha",
        tags=["p2"],
        status="pending",
        meta={"priority": 2},
    )
    bug = svc.store_item(
        project="proj-x",
        project_id=None,
        item_type="bug",
        title="Bug B",
        body_md="beta",
        tags=["sev:low"],
        status="pending",
        meta={"severity": "low"},
    )

    # replace_body bumps version for any type
    todo2 = svc.replace_body(project="proj-x", project_id=None, item_id=todo.id, new_body="alpha2", expected_version=1)
    assert todo2.version == 2 and todo2.body_md == "alpha2"
    bug2 = svc.replace_body(project="proj-x", project_id=None, item_id=bug.id, new_body="beta2", expected_version=1)
    assert bug2.version == 2 and bug2.body_md == "beta2"

