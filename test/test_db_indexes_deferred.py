from pathlib import Path
from utils.database import DuckDBManager, DocumentRow, ChunkRow
from utils.config import DatabaseConfig


def test_create_indexes_can_run_after_inserts(tmp_path):
    db_path = tmp_path / "rag_perf.duckdb"
    cfg = DatabaseConfig(path=db_path)
    manager = DuckDBManager(cfg, embedding_dim=4)
    manager.reset()
    manager.initialize_schema()

    # Insert minimal data
    docs = [DocumentRow(doc_id="d1", url="http://example.com", title="t", fingerprint="f")] 
    chunks = [
        ChunkRow(
            chunk_id="c1",
            doc_id="d1",
            section_path="Document",
            position=0,
            text="hello world",
            fingerprint="ff",
            embedding=[0.1, 0.2, 0.3, 0.4],
        )
    ]
    manager.insert_documents(docs)
    manager.insert_chunks(chunks)

    # Should not raise even if extensions are missing
    manager.create_indexes()
    # Idempotency
    manager.create_indexes()

    # Sanity: database file exists and is non-empty
    assert db_path.exists() and db_path.stat().st_size > 0

