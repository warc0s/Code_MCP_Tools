import math
from typing import Any, Dict, List

import pytest

from utils.config import RetrievalConfig
from utils.retrieval import Retriever


class FakeCursor:
    def __init__(self, rows: List[tuple]):
        self._rows = rows

    def fetchall(self) -> List[tuple]:
        return list(self._rows)


class FakeConnection:
    def __init__(self) -> None:
        self.executed: List[Dict[str, Any]] = []

    def execute(self, sql: str, parameters: Any = None) -> FakeCursor:
        self.executed.append({"sql": sql, "parameters": parameters})
        rows = [
            (
                "chunk-1",
                "doc-1",
                "https://example.com/a",
                "Title A",
                "Section > Subsection",
                0,
                "Example text block.",
                1.2345,
                [0.0, 0.0, 0.0],
            )
        ]
        return FakeCursor(rows)


class DummyEmbedder:
    embedding_dim = 3

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [[0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, query: str) -> List[float]:
        return [0.0, 0.0, 0.0]


def make_config() -> RetrievalConfig:
    return RetrievalConfig(
        dense_topk=4,
        lexical_topk=6,
        hybrid_alpha=0.5,
        mmr_lambda=0.5,
        same_url_penalty=0.08,
        final_k=6,
        force_english_queries=True,
        rerank_topk=4,
        enable_rerank=False,
    )


def test_lexical_search_uses_fts_bm25():
    conn = FakeConnection()
    retriever = Retriever(
        connection=conn,
        config=make_config(),
        embedder=DummyEmbedder(),
        reranker=None,
    )

    results = retriever.lexical_search("test query")

    assert conn.executed, "Se esperaba una consulta ejecutada sobre DuckDB."
    executed_sql = conn.executed[0]["sql"].lower()
    assert "match" in executed_sql, "La consulta debe usar MATCH del índice FTS."
    assert "bm25" in executed_sql, "La consulta debe ordenar con BM25."
    assert results, "La búsqueda debe devolver al menos un resultado."
    first = results[0]
    for key in ("chunk_id", "doc_id", "url", "title", "section_path", "position", "score"):
        assert key in first, f"Falta el metadato obligatorio {key}."


def test_hybrid_search_normalizes_scores_and_applies_mmr(monkeypatch):
    conn = FakeConnection()
    retriever = Retriever(
        connection=conn,
        config=make_config(),
        embedder=DummyEmbedder(),
        reranker=None,
    )

    dense_candidates = [
        {
            "chunk_id": "c1",
            "doc_id": "d1",
            "url": "https://example.com/a",
            "title": "A1",
            "section_path": "A > 1",
            "position": 0,
            "text": "dense one",
            "score": 0.9,
        },
        {
            "chunk_id": "c2",
            "doc_id": "d2",
            "url": "https://example.com/b",
            "title": "B1",
            "section_path": "B > 1",
            "position": 1,
            "text": "dense two",
            "score": 0.8,
        },
    ]

    lexical_candidates = [
        {
            "chunk_id": "c3",
            "doc_id": "d3",
            "url": "https://example.com/a",
            "title": "A2",
            "section_path": "A > 2",
            "position": 2,
            "text": "lex one",
            "score": 8.0,
        },
        {
            "chunk_id": "c4",
            "doc_id": "d4",
            "url": "https://example.com/c",
            "title": "C1",
            "section_path": "C > 1",
            "position": 0,
            "text": "lex two",
            "score": 5.0,
        },
    ]

    monkeypatch.setattr(retriever, "_dense_candidates", lambda q, top_k: dense_candidates)
    monkeypatch.setattr(retriever, "_lexical_candidates", lambda q, top_k: lexical_candidates)
    monkeypatch.setattr(retriever, "_generate_embeddings", lambda q: [0.1, 0.1, 0.1])

    results = retriever.hybrid_search("hybrid query")

    assert results, "La búsqueda híbrida debe devolver resultados."
    assert len(results) <= retriever.config.final_k

    scores = [r["score"] for r in results]
    assert all(0.0 <= s <= 1.0 for s in scores), "Las puntuaciones deben quedar normalizadas en [0, 1]."

    urls = [r["url"] for r in results[:2]]
    assert len(set(urls)) > 1, "MMR y la penalización por URL deben diversificar los primeros resultados."
