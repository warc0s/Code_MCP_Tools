from __future__ import annotations

import duckdb

import app as app_mod
from app import _rag_schema_available, load_retriever
from utils.config import AppConfig, DatabaseConfig
from utils.database import ChunkRow, DocumentRow, DuckDBManager


def test_rag_schema_available_rejects_incomplete_columns(tmp_path) -> None:
    db_path = tmp_path / "partial.duckdb"
    connection = duckdb.connect(db_path.as_posix())
    try:
        connection.execute("CREATE TABLE docs (doc_id TEXT);")
        connection.execute("CREATE TABLE chunks (chunk_id TEXT);")
    finally:
        connection.close()

    assert _rag_schema_available(db_path) is False


def test_load_retriever_rejects_incompatible_metadata_before_embedding_provider(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "rag.duckdb"
    manager = DuckDBManager(DatabaseConfig(path=db_path), embedding_dim=2)
    manager.reset()
    manager.initialize_schema()
    manager.insert_documents(
        [
            DocumentRow(
                doc_id="doc-1",
                url="https://example.com/doc",
                title="Doc",
                fingerprint="doc-fp",
            )
        ]
    )
    manager.insert_chunks(
        [
            ChunkRow(
                chunk_id="chunk-1",
                doc_id="doc-1",
                section_path="Intro",
                position=0,
                text="hello",
                fingerprint="chunk-fp",
                embedding=[1.0, 0.0],
            )
        ]
    )
    manager.write_metadata(
        {
            "runtime_mode": "cloud",
            "embedding_model_name": "fake-embedder",
            "embedding_dim": "2",
        }
    )
    manager.teardown()

    def fail_embedding_provider(*_args, **_kwargs):
        raise AssertionError("EmbeddingProvider should not be created for incompatible RAG metadata")

    monkeypatch.setattr(app_mod, "EmbeddingProvider", fail_embedding_provider)
    config = AppConfig.from_dict(
        {
            "database": {"path": str(db_path)},
            "embeddings": {"model_name": "fake-embedder", "embedding_dim": 2},
        }
    )

    retriever, connection = load_retriever(config)
    try:
        assert retriever is None
        assert connection is not None
        assert connection.execute("SELECT COUNT(*) FROM docs;").fetchone()[0] == 1
    finally:
        if connection is not None:
            connection.close()
