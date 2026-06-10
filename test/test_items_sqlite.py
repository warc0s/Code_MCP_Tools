from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sys
from pathlib import Path as _Path
import pytest

# Ensure repository root in sys.path for local imports
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.config import MemoryDatabaseConfig
from utils.memory_db import bootstrap_memory_db, _connect as memory_connect
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
        meta={
            "topic": "t",
            "decision": "d",
            "context": "c",
            "rationale": "r",
            "related_links": [],
        },
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


def test_replace_body_is_idempotent_for_identical_content(tmp_path):
    cfg = MemoryDatabaseConfig(path=tmp_path / "memory.sqlite3")
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("body-check")
    rec = svc.store_item(
        project="body-check",
        project_id=None,
        item_type="doc",
        title="Doc",
        body_md="same",
        tags=[],
        status="pending",
        meta={},
        typed={},
    )

    unchanged = svc.replace_body(
        project="body-check",
        project_id=None,
        item_id=rec.id,
        new_body="same",
        expected_version=rec.version,
    )

    assert unchanged.body_md == "same"
    assert unchanged.version == rec.version


def test_create_project_is_atomic_and_idempotent_under_concurrency(tmp_path):
    cfg = MemoryDatabaseConfig(path=tmp_path / "memory.sqlite3")
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    barrier = threading.Barrier(8)

    def create_once():
        barrier.wait(timeout=5)
        return svc.create_project("race-create")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: create_once(), range(8)))

    assert len({result["id"] for result in results}) == 1
    assert sum(1 for result in results if result["created"]) == 1
    assert sum(1 for result in results if not result["created"]) == 7


def test_create_project_rejects_invalid_reserved_and_short_slugs(tmp_path):
    cfg = MemoryDatabaseConfig(path=tmp_path / "memory.sqlite3")
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)

    for slug in ("", "ab", "api", "x" * 65):
        with pytest.raises(ValueError):
            svc.create_project(slug)


def test_sqlite_read_only_connections_reject_writes(tmp_path):
    cfg = MemoryDatabaseConfig(path=tmp_path / "memory.sqlite3")
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("readonly")

    with memory_connect(cfg.path, read_only=True) as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO projects (id, slug, name) VALUES ('x', 'x', 'X');")

    with svc._connect(read_only=True) as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE projects SET name = 'Changed' WHERE slug = 'readonly';")


def test_list_items_rejects_invalid_status_filter(tmp_path):
    cfg = MemoryDatabaseConfig(path=tmp_path / "memory.sqlite3")
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("status-check")
    rec = svc.store_item(
        project="status-check",
        project_id=None,
        item_type="memory",
        title="Status memory",
        body_md="Alpha",
        tags=[],
        status="pending",
        meta={},
        typed={
            "topic": "topic",
            "decision": "decision",
            "context": "context",
            "rationale": "rationale",
        },
    )

    matches = svc.list_items(project="status-check", project_id=None, status=" PENDING ")
    assert [item.id for item in matches] == [rec.id]
    with pytest.raises(ValueError):
        svc.list_items(project="status-check", project_id=None, status="bogus")


def test_delete_project_is_atomic_for_concurrent_calls(tmp_path):
    cfg = MemoryDatabaseConfig(path=tmp_path / "memory.sqlite3")
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("race-project")
    for index in range(3):
        svc.store_item(
            project="race-project",
            project_id=None,
            item_type="doc",
            title=f"Doc {index}",
            body_md="Body",
            tags=[],
            status="pending",
            meta={},
            typed={},
        )

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def delete_once():
        try:
            barrier.wait(timeout=5)
            results.append(svc.delete_project(project="race-project", project_id=None))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=delete_once), threading.Thread(target=delete_once)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(results) == 1
    assert results[0]["deleted_items"] == 3
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert not svc.project_exists("race-project")
