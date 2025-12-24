from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app import _open_ro_connection


def test_open_ro_connection_is_read_only(tmp_path: Path):
    db_path = tmp_path / "rag.duckdb"
    conn = duckdb.connect(db_path.as_posix())
    try:
        conn.execute("CREATE TABLE docs(doc_id TEXT);")
        conn.execute("CREATE TABLE chunks(chunk_id TEXT);")
    finally:
        conn.close()

    ro = _open_ro_connection(db_path)
    try:
        with pytest.raises(Exception):  # duckdb raises a runtime error on writes in RO
            ro.execute("CREATE TABLE should_fail(i INTEGER);")
    finally:
        ro.close()

