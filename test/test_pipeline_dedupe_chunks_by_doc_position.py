from __future__ import annotations

from pathlib import Path

from utils.crawling import CrawledDocument
from utils.config import AppConfig

import utils.pipeline as pipeline_mod


class _FakeEmbedder:
    model_name = "fake-embedder"
    embedding_dim = 2

    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig.from_dict(
        {
            "database": {"path": str(tmp_path / "rag.duckdb")},
            "chunking": {
                "max_tokens": 80,
                "overlap_tokens": 0,
                "min_chunk_tokens": 1,
            },
        }
    )


def test_rebuild_keeps_duplicate_chunk_fingerprints_for_distinct_documents(tmp_path, monkeypatch):
    managed_managers: list[object] = []

    class FakeManager:
        def __init__(self, config, embedding_dim):
            self.path = Path(config.path)
            self.embedding_dim = embedding_dim
            self.teardown_called = False
            self.inserted_docs = []
            self.inserted_chunks = []
            managed_managers.append(self)

        def reset(self):
            pass

        def initialize_schema(self):
            pass

        def insert_documents(self, rows):
            self.inserted_docs = list(rows)

        def insert_chunks(self, rows):
            self.inserted_chunks = list(rows)

        def create_indexes(self):
            pass

        def write_metadata(self, entries):
            self.path.write_text("ok", encoding="utf-8")

        def teardown(self):
            self.teardown_called = True

    def _chunk_document(_markdown: str, _chunking):
        return [
            {
                "text": "shared chunk text",
                "section_path": "intro",
                "position": 0,
                "fingerprint": "shared-fingerprint",
            }
        ]

    monkeypatch.setattr(pipeline_mod, "DuckDBManager", FakeManager)
    monkeypatch.setattr(pipeline_mod, "chunk_document", _chunk_document)

    docs = [
        CrawledDocument(
            url="https://example.com/a",
            title="Doc A",
            markdown="ignored text A",
            fingerprint="doc-fingerprint-a",
        ),
        CrawledDocument(
            url="https://example.com/b",
            title="Doc B",
            markdown="ignored text B",
            fingerprint="doc-fingerprint-b",
        ),
    ]

    summary = pipeline_mod._rebuild_rag_from_crawled_documents(docs, _config(tmp_path), _FakeEmbedder())

    assert summary.documents == 2
    assert summary.chunks == 2

    assert managed_managers, "expected a fake DB manager to have been instantiated"
    manager = managed_managers[0]
    assert manager.teardown_called is True
    assert len(manager.inserted_docs) == 2
    assert len(manager.inserted_chunks) == 2
    assert manager.inserted_chunks[0].fingerprint == "shared-fingerprint"
    assert manager.inserted_chunks[1].fingerprint == "shared-fingerprint"
    assert manager.inserted_chunks[0].doc_id != manager.inserted_chunks[1].doc_id
