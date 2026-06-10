from __future__ import annotations

import pytest

from utils.config import RetrievalConfig
from utils.retrieval import Retriever


class FakeConnection:
    def execute(self, *args, **kwargs):
        raise AssertionError("connection should not be used for invalid top_k")


class FakeEmbedder:
    def embed_query(self, query):
        raise AssertionError("embedder should not be used for invalid top_k")


def test_dense_candidates_rejects_invalid_top_k_before_embedding():
    retriever = Retriever(FakeConnection(), RetrievalConfig(), FakeEmbedder())

    with pytest.raises(ValueError, match="top_k"):
        retriever._dense_candidates("query", top_k=0)


def test_lexical_candidates_rejects_invalid_top_k_before_querying():
    retriever = Retriever(FakeConnection(), RetrievalConfig(), FakeEmbedder())

    with pytest.raises(ValueError, match="top_k"):
        retriever._lexical_candidates("query", top_k=-1)


def _candidate(index: int) -> dict:
    return {
        "chunk_id": f"c{index}",
        "doc_id": f"d{index}",
        "url": f"https://example.com/{index}",
        "title": f"Doc {index}",
        "section_path": "",
        "position": index,
        "text": f"Chunk {index}",
        "score": float(100 - index),
        "embedding": [1.0, float(index) / 10.0],
    }


def test_hybrid_search_respects_top_k_without_reranker():
    config = RetrievalConfig(final_k=2, enable_rerank=False)
    retriever = Retriever(None, config, FakeEmbedder())
    retriever._dense_candidates = lambda query, top_k=None: [_candidate(i) for i in range(8)]
    retriever._lexical_candidates = lambda query, top_k=None: []

    results = retriever.hybrid_search("query", top_k=5)

    assert len(results) == 5
    assert all("embedding" not in item for item in results)


def test_hybrid_search_respects_top_k_with_reranker():
    class FakeReranker:
        seen_top_k = None

        def rerank(self, query, candidates, top_k):
            self.seen_top_k = top_k
            return list(reversed(candidates))[:top_k]

    reranker = FakeReranker()
    config = RetrievalConfig(final_k=2, enable_rerank=True, rerank_topk=12)
    retriever = Retriever(None, config, FakeEmbedder(), reranker=reranker)
    retriever._dense_candidates = lambda query, top_k=None: [_candidate(i) for i in range(8)]
    retriever._lexical_candidates = lambda query, top_k=None: []

    results = retriever.hybrid_search("query", top_k=4)

    assert len(results) == 4
    assert reranker.seen_top_k == 4


def test_lexical_like_fallback_escapes_wildcards():
    class RecordingResult:
        def __init__(self, rows):
            self._rows = rows

        def fetchone(self):
            return None

        def fetchall(self):
            return self._rows

    class RecordingConnection:
        sql = ""
        params = []

        def execute(self, sql, params=None):
            if "information_schema.tables" not in sql:
                self.sql = sql
                self.params = list(params or [])
            return RecordingResult([])

    connection = RecordingConnection()
    retriever = Retriever(connection, RetrievalConfig(), FakeEmbedder())

    assert retriever._lexical_candidates("foo% bar_", top_k=3) == []
    assert "ESCAPE '\\'" in connection.sql
    assert "%foo\\%%" in connection.params
    assert "%bar\\_%" in connection.params
