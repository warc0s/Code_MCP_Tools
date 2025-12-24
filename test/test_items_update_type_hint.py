from __future__ import annotations

import sys
from pathlib import Path as _Path

import pytest

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.config import MemoryDatabaseConfig
from utils.items import ItemService
from utils.memory_db import bootstrap_memory_db


def test_update_item_type_hint_allows_matching_type(tmp_path) -> None:
    cfg = MemoryDatabaseConfig(path=tmp_path / "memory.sqlite3")
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("p1")
    rec = svc.store_item(
        project="p1",
        project_id=None,
        item_type="bug",
        title="B1",
        body_md="",
        tags=[],
        status="pending",
        meta={
            "severity": "low",
            "reproduction": "steps",
            "expected": "ok",
            "root_cause": "rc",
        },
    )
    updated = svc.update_item(
        project="p1",
        project_id=None,
        item_id=rec.id,
        fields={"type": "bug", "title": "B1 updated"},
    )
    assert updated.type == "bug"
    assert updated.title == "B1 updated"


def test_update_item_type_hint_rejects_mismatch(tmp_path) -> None:
    cfg = MemoryDatabaseConfig(path=tmp_path / "memory.sqlite3")
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("p1")
    rec = svc.store_item(
        project="p1",
        project_id=None,
        item_type="bug",
        title="B1",
        body_md="",
        tags=[],
        status="pending",
        meta={
            "severity": "low",
            "reproduction": "steps",
            "expected": "ok",
            "root_cause": "rc",
        },
    )
    with pytest.raises(ValueError, match=r"Item type mismatch"):
        svc.update_item(
            project="p1",
            project_id=None,
            item_id=rec.id,
            fields={"type": "todo", "title": "B1 updated"},
        )

