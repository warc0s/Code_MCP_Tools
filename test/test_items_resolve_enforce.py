from __future__ import annotations

from pathlib import Path as _Path
import pytest

from utils.config import MemoryDatabaseConfig
from utils.memory_db import bootstrap_memory_db
from utils.items import ItemService


def _make_db(path: str = "data/test_memory_resolve.sqlite3") -> MemoryDatabaseConfig:
    p = _Path(path)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
    return MemoryDatabaseConfig(path=p)


def _long_text(n: int = 130) -> str:
    return ("x" * n) + " done"


@pytest.mark.parametrize("itype", ["bug", "todo"])
def test_resolving_requires_done_summary_and_related_files(itype: str):
    cfg = _make_db()
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)
    svc.create_project("p1")
    # Create with minimal valid meta for each type
    base_meta = {
        "bug": {"severity": "low", "reproduction": "steps", "expected": "ok", "root_cause": "rc"},
        "todo": {"kind": "feature", "acceptance_criteria": ["a"], "dependencies": [], "priority": "p2"},
    }[itype]
    item = svc.store_item(
        project="p1",
        project_id=None,
        item_type=itype,
        title=f"Item {itype}",
        body_md="",
        tags=[],
        status="pending",
        meta=base_meta,
    )

    # Attempt to resolve without required fields should fail
    with pytest.raises(Exception):
        svc.update_item(project="p1", project_id=None, item_id=item.id, fields={"status": "resolved"})

    # Provide done_summary but no files: still fail
    with pytest.raises(Exception):
        svc.update_item(
            project="p1",
            project_id=None,
            item_id=item.id,
            fields={"status": "resolved", "meta": {**item.meta, "done_summary": _long_text() }},
        )

    # Provide both done_summary and related_files: succeeds
    updated = svc.update_item(
        project="p1",
        project_id=None,
        item_id=item.id,
        fields={
            "status": "resolved",
            "meta": {**item.meta, "done_summary": _long_text(), "related_files": ["utils/items.py"]},
        },
    )
    assert updated.status == "resolved"

