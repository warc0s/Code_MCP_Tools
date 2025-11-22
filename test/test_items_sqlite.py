from __future__ import annotations

import os
from pathlib import Path

import sys
from pathlib import Path as _Path

# Ensure repository root in sys.path for local imports
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.config import MemoryDatabaseConfig
from utils.memory_db import bootstrap_memory_db
from utils.items import ItemService


def make_temp_db(path: str = "data/test_memory.sqlite3") -> MemoryDatabaseConfig:
    p = Path(path)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            # Best-effort cleanup
            pass
    return MemoryDatabaseConfig(path=p)


def test_item_service_crud_sqlite():
    cfg = make_temp_db()
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)

    # Create project
    proj = svc.create_project("test-proj", name="Test Project")
    assert proj["slug"] == "test-proj"
    assert proj["created"] is True

    # Create again: idempotent
    proj2 = svc.create_project("test-proj")
    assert proj2["id"] == proj["id"]
    assert proj2["created"] is False

    # Store item
    rec = svc.store_item(
        project="test-proj",
        project_id=None,
        item_type="memory",
        title="First memory",
        body_md="Alpha",
        tags=["a", "B"],
        status="pending",
        meta={"k": 1},
    )
    assert rec.project_slug == "test-proj"
    assert rec.version == 1
    assert "a" in rec.tags and "b" in rec.tags

    # Update metadata
    rec = svc.update_item(
        project="test-proj",
        project_id=None,
        item_id=rec.id,
        fields={"title": "Updated title", "status": "in_progress"},
    )
    assert rec.title == "Updated title"
    assert rec.status == "in_progress"
    assert rec.version == 2

    # Replace body bumps version
    rec = svc.replace_body(
        project="test-proj",
        project_id=None,
        item_id=rec.id,
        new_body="Beta",
        expected_version=2,
    )
    assert rec.body_md == "Beta"
    assert rec.version == 3

    # Search
    results = svc.search_items(
        project="test-proj",
        project_id=None,
        query="beta",
        item_type="memory",
        tags=[],
        limit=10,
    )
    assert any(r.id == rec.id for r in results)

    # Delete item
    svc.delete_item(project="test-proj", project_id=None, item_id=rec.id)
    items = svc.list_items(project="test-proj", project_id=None, item_type="memory")
    assert len(items) == 0

    # Delete project
    summary = svc.delete_project(project="test-proj", project_id=None)
    assert summary["deleted_items"] >= 0
    assert summary["deleted_projects"] == 1
