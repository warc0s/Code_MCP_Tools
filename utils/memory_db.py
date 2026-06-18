"""
SQLite bootstrap for projects/items memory store.

Creates the required schema if it does not exist and enforces foreign keys.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from utils.config import MemoryDatabaseConfig


def _connect(db_path: Path, read_only: bool = False) -> sqlite3.Connection:
    db_path = Path(db_path)
    if read_only:
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path.as_posix())
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
    except Exception:
        pass
    return conn


def bootstrap_memory_db(config: MemoryDatabaseConfig) -> None:
    """Create the SQLite database for projects/items if it does not exist.

    Idempotent: it preserves existing data and only creates missing tables/indexes.
    """
    path = Path(config.path)
    with _connect(path, read_only=False) as conn:
        # projects
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # items (base columns)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('memory', 'doc', 'bug', 'todo')),
                title TEXT NOT NULL,
                body_md TEXT,
                tags TEXT,
                status TEXT,
                meta TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            """
        )
        # Ensure typed columns exist (added progressively). We keep TEXT storage (JSON for arrays).
        cur = conn.execute("PRAGMA table_info(items);")
        cols = {row[1] for row in cur.fetchall()}
        def add_col(name: str, decl: str = "TEXT"):
            if name not in cols:
                try:
                    conn.execute(f"ALTER TABLE items ADD COLUMN {name} {decl};")
                except Exception:
                    pass
        # memory typed
        add_col("memory_topic")
        add_col("memory_decision")
        add_col("memory_context")
        add_col("memory_rationale")
        add_col("memory_related_links")  # JSON array in TEXT
        # doc typed (optional fields kept in meta; authors/related_docs exposed as typed)
        add_col("doc_authors")           # JSON array in TEXT
        add_col("doc_related_docs")      # JSON array in TEXT
        # bug typed (required for create)
        add_col("bug_severity")
        add_col("bug_reproduction")
        add_col("bug_expected")
        add_col("bug_root_cause")
        # todo typed (required for create)
        add_col("todo_kind")
        add_col("todo_acceptance_criteria")  # JSON array in TEXT
        add_col("todo_priority")
        # metadata (optional small key/value store for UI)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        # indexes
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_items_project_id ON items(project_id);")
        except Exception:
            pass
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);")
        except Exception:
            pass


__all__ = ["bootstrap_memory_db"]
