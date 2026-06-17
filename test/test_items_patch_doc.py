from __future__ import annotations

import sys
from pathlib import Path as _Path

# Ensure repository root in sys.path for local imports
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.config import MemoryDatabaseConfig
from utils.memory_db import bootstrap_memory_db
from utils.items import ItemService


def make_temp_db(path: str = "data/test_memory_patch.sqlite3") -> MemoryDatabaseConfig:
    p = _Path(path)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
    return MemoryDatabaseConfig(path=p)


def test_patch_doc_unified_diff():
    cfg = make_temp_db()
    bootstrap_memory_db(cfg)
    svc = ItemService(cfg)

    # Prepare project and doc item.
    proj = svc.create_project("patch-proj", name="Patch Project")
    assert proj["slug"] == "patch-proj"

    body = "Alpha\nBeta\nGamma\n"
    item = svc.store_item(
        project="patch-proj",
        project_id=None,
        item_type="doc",
        title="Doc to patch",
        body_md=body,
        tags=["x"],
        status="pending",
        meta={},
    )
    assert item.version == 1

    # Change the second line (Beta -> Beta 2).
    diff = """@@ -2,1 +2,1 @@
-Beta
+Beta 2
"""
    updated = svc.patch_doc(
        project="patch-proj",
        project_id=None,
        item_id=item.id,
        unified_diff=diff,
        expected_version=1,
    )

    assert updated.version == 2
    assert "Beta 2" in updated.body_md and "Alpha" in updated.body_md and "Gamma" in updated.body_md
