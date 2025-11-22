"""
Gestión de la base de datos DuckDB usada como almacén vectorial.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import duckdb

from utils.config import DatabaseConfig


@dataclass
class DocumentRow:
    doc_id: str
    url: str
    title: str
    fingerprint: str


@dataclass
class ChunkRow:
    chunk_id: str
    doc_id: str
    section_path: str
    position: int
    text: str
    fingerprint: str
    embedding: Sequence[float]


class DuckDBManager:
    def __init__(self, config: DatabaseConfig, embedding_dim: int):
        self.config = config
        self.embedding_dim = embedding_dim
        self.path = Path(config.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: duckdb.DuckDBPyConnection | None = None

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._connection is None:
            self._prepare_extension_directory()
            self._connection = duckdb.connect(self.path.as_posix())
            self._install_extensions()
        return self._connection

    def _prepare_extension_directory(self) -> None:
        base = Path(".duckdb/extensions")
        base.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("DUCKDB_EXTENSION_DIRECTORY", str(base.resolve()))

    def _set_foreign_keys(self, enabled: bool) -> None:
        conn = self._connection
        if not conn:
            return
        try:
            value = "ON" if enabled else "OFF"
            conn.execute(f"PRAGMA foreign_keys={value};")
        except Exception:
            # Algunas versiones de DuckDB no soportan PRAGMA foreign_keys; ignoramos
            pass

    def _install_extensions(self) -> None:
        conn = self._connection
        assert conn is not None
        for extension in ("vss", "fts"):
            try:
                conn.execute(f"LOAD {extension};")
            except Exception:
                try:
                    conn.execute(f"INSTALL {extension};")
                    conn.execute(f"LOAD {extension};")
                except Exception as exc:
                    raise RuntimeError(
                        f"No fue posible instalar la extensión '{extension}'. "
                        "Asegúrate de tener conectividad para descargarla al menos una vez."
                    ) from exc

        # Habilita la persistencia experimental de índices HNSW en DuckDB (requerido para almacenar en disco)
        try:
            conn.execute("SET hnsw_enable_experimental_persistence = true;")
        except Exception:
            try:
                conn.execute("PRAGMA hnsw_enable_experimental_persistence=true;")
            except Exception as exc:
                raise RuntimeError(
                    "No se pudo habilitar la persistencia experimental de HNSW. "
                    "Actualiza DuckDB o desactiva la creación de índice HNSW."
                ) from exc

    def reset(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None
        self._prepare_extension_directory()
        self._connection = duckdb.connect(self.path.as_posix())
        self._install_extensions()

    def initialize_schema(self) -> None:
        conn = self.connection
        conn.execute("DROP TABLE IF EXISTS chunks;")
        conn.execute("DROP TABLE IF EXISTS docs;")
        conn.execute("DROP TABLE IF EXISTS metadata;")
        # Nota: projects/items viven en la base SQLite de memoria; sólo se gestiona aquí el esquema RAG
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS docs (
                doc_id TEXT PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                fingerprint TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            f"""
            CREATE TABLE chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                section_path TEXT,
                position INTEGER,
                text TEXT NOT NULL,
                fingerprint TEXT,
                embedding FLOAT[{self.embedding_dim}],
                FOREIGN KEY(doc_id) REFERENCES docs(doc_id)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        # 'items' ahora vive en la base SQLite de memoria; no crear índices aquí
        conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_url ON docs(url);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);")
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw(embedding) WITH (metric='cosine');"
            )
        except Exception:
            # Si la versión de DuckDB/VSS no soporta persistencia HNSW, continuamos sin índice vectorial
            pass
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks USING fts(text) WITH (stopwords='english');"
            )
        except Exception:
            # Si la versión de FTS no soporta esta sintaxis, continuamos sin índice
            pass
        # FKs permanecen activadas; no es necesario togglear para este rebuild

    def insert_documents(self, rows: Iterable[DocumentRow]) -> None:
        conn = self.connection
        conn.executemany(
            "INSERT INTO docs (doc_id, url, title, fingerprint) VALUES (?, ?, ?, ?);",
            [(r.doc_id, r.url, r.title, r.fingerprint) for r in rows],
        )

    def insert_chunks(self, rows: Iterable[ChunkRow]) -> None:
        conn = self.connection
        conn.executemany(
            """
            INSERT INTO chunks (chunk_id, doc_id, section_path, position, text, fingerprint, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            [
                (
                    r.chunk_id,
                    r.doc_id,
                    r.section_path,
                    r.position,
                    r.text,
                    r.fingerprint,
                    list(map(float, r.embedding)),
                )
                for r in rows
            ],
        )
        conn.execute("CHECKPOINT;")

    def write_metadata(self, entries: Mapping[str, str]) -> None:
        conn = self.connection
        conn.executemany(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?);",
            [(str(key), "" if value is None else str(value)) for key, value in entries.items()],
        )
        conn.execute("CHECKPOINT;")

    def teardown(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None


def read_metadata(connection: duckdb.DuckDBPyConnection) -> dict[str, str]:
    try:
        rows = connection.execute("SELECT key, value FROM metadata;").fetchall()
    except Exception:
        return {}
    return {str(key): "" if value is None else str(value) for key, value in rows}

__all__ = ["DuckDBManager", "DocumentRow", "ChunkRow", "read_metadata"]
