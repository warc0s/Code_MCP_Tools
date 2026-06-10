from __future__ import annotations

from pathlib import Path

import pytest

import utils.pipeline as pipeline_mod
from utils.config import AppConfig
from utils.crawling import CrawledDocument


class FakeEmbedder:
    model_name = "fake-embedder"
    embedding_dim = 2

    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _config(tmp_path):
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


def _doc():
    return CrawledDocument(
        url="https://example.com/doc",
        title="Doc",
        markdown="# Title\n\nAlpha beta gamma delta.",
        fingerprint="doc-fp",
    )


def test_rebuild_tears_down_manager_after_success(tmp_path, monkeypatch):
    instances = []
    destination = tmp_path / "rag.duckdb"

    class FakeManager:
        def __init__(self, config, embedding_dim):
            self.config = config
            self.embedding_dim = embedding_dim
            self.path = Path(config.path)
            self.teardown_called = False
            self.inserted_chunks = []
            instances.append(self)

        def reset(self): pass
        def initialize_schema(self): pass
        def insert_documents(self, rows): self.inserted_docs = list(rows)
        def insert_chunks(self, rows): self.inserted_chunks = list(rows)
        def create_indexes(self): pass
        def write_metadata(self, entries):
            self.metadata = dict(entries)
            self.path.write_text("new-db", encoding="utf-8")
        def teardown(self): self.teardown_called = True

    monkeypatch.setattr(pipeline_mod, "DuckDBManager", FakeManager)

    summary = pipeline_mod._rebuild_rag_from_crawled_documents(
        [_doc()],
        _config(tmp_path),
        FakeEmbedder(),
    )

    assert summary.documents == 1
    assert summary.chunks == 1
    assert instances[0].teardown_called is True
    assert instances[0].inserted_chunks
    assert destination.read_text(encoding="utf-8") == "new-db"


def test_rebuild_tears_down_manager_after_insert_failure(tmp_path, monkeypatch):
    instances = []
    destination = tmp_path / "rag.duckdb"
    destination.write_text("old-db", encoding="utf-8")

    class FailingManager:
        def __init__(self, config, embedding_dim):
            self.path = Path(config.path)
            self.teardown_called = False
            instances.append(self)

        def reset(self): self.path.write_text("partial-db", encoding="utf-8")
        def initialize_schema(self): pass
        def insert_documents(self, rows): pass
        def insert_chunks(self, rows):
            raise RuntimeError("insert failed")
        def create_indexes(self): pass
        def write_metadata(self, entries): pass
        def teardown(self): self.teardown_called = True

    monkeypatch.setattr(pipeline_mod, "DuckDBManager", FailingManager)

    with pytest.raises(RuntimeError, match="insert failed"):
        pipeline_mod._rebuild_rag_from_crawled_documents(
            [_doc()],
            _config(tmp_path),
            FakeEmbedder(),
        )

    assert instances[0].teardown_called is True
    assert destination.read_text(encoding="utf-8") == "old-db"
    assert not instances[0].path.exists()


def test_replace_database_atomically_keeps_destination_on_initial_replace_failure(tmp_path, monkeypatch):
    destination = tmp_path / "rag.duckdb"
    staging = tmp_path / ".rag.duckdb.tmp"
    destination.write_text("old-db", encoding="utf-8")
    staging.write_text("new-db", encoding="utf-8")
    real_replace = pipeline_mod.os.replace

    def fail_first_replace(src, dst):
        if Path(src) == destination:
            raise OSError("destination locked")
        return real_replace(src, dst)

    monkeypatch.setattr(pipeline_mod.os, "replace", fail_first_replace)

    with pytest.raises(OSError, match="destination locked"):
        pipeline_mod._replace_database_atomically(staging, destination)

    assert destination.read_text(encoding="utf-8") == "old-db"
    assert not staging.exists()


def test_replace_database_atomically_restores_destination_on_staging_failure(tmp_path, monkeypatch):
    destination = tmp_path / "rag.duckdb"
    staging = tmp_path / ".rag.duckdb.tmp"
    destination.write_text("old-db", encoding="utf-8")
    staging.write_text("new-db", encoding="utf-8")
    real_replace = pipeline_mod.os.replace

    def fail_staging_replace(src, dst):
        if Path(src) == staging:
            raise OSError("staging failed")
        return real_replace(src, dst)

    monkeypatch.setattr(pipeline_mod.os, "replace", fail_staging_replace)

    with pytest.raises(OSError, match="staging failed"):
        pipeline_mod._replace_database_atomically(staging, destination)

    assert destination.read_text(encoding="utf-8") == "old-db"
    assert not staging.exists()
