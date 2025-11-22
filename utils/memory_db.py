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
    # SQLite URI for read-only if needed; here we keep read_write to allow bootstrap
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path.as_posix())
    # Enforce FK constraints
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
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
        # items
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

