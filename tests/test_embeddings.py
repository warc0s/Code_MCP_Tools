from __future__ import annotations

import pytest

from utils.config import EmbeddingConfig
from utils.embeddings import EmbeddingProvider


class DummyVector:
    def __init__(self, data):
        self._data = data

    def tolist(self):
        return self._data


class DummyMatrix:
    def __init__(self, data):
        self._rows = [DummyVector(row) for row in data]

    def tolist(self):
        return [row.tolist() for row in self._rows]

    def __getitem__(self, index):
        return self._rows[index]


def test_embedding_provider_uses_cpu_defaults(monkeypatch):
    recorded = {}

    class DummySentenceTransformer:
        def __init__(self, model_name):
            recorded["model_name"] = model_name

        def get_sentence_embedding_dimension(self):
            return 2

        def encode(self, texts, **kwargs):
            return DummyMatrix([[0.0, 0.0] for _ in texts])

    monkeypatch.setattr(
        EmbeddingProvider,
        "_load_sentence_transformer",
        lambda self: DummySentenceTransformer,
    )

    provider = EmbeddingProvider(EmbeddingConfig())
    vector = provider.embed_query("hola")

    assert vector == [0.0, 0.0]
    assert recorded["model_name"] == EmbeddingConfig().model_name


def test_embedding_provider_reports_missing_torch(monkeypatch):
    def fail_import(self):
        raise ImportError(
            "Could not import module 'AutoModelForSequenceClassification'. Are this object's requirements defined correctly?"
        )

    monkeypatch.setattr(EmbeddingProvider, "_load_sentence_transformer", fail_import)

    provider = EmbeddingProvider(EmbeddingConfig())

    with pytest.raises(RuntimeError) as err:
        provider.embed_query("hola")

    assert "torch" in str(err.value)


def test_embedding_provider_reports_missing_six(monkeypatch):
    def fail_import(self):
        raise ImportError("Could not import module 'GenerationMixin'.") from ModuleNotFoundError(
            "No module named 'six'"
        )

    monkeypatch.setattr(EmbeddingProvider, "_load_sentence_transformer", fail_import)

    provider = EmbeddingProvider(EmbeddingConfig())

    with pytest.raises(RuntimeError) as err:
        provider.embed_query("hola")

    assert "`six`" in str(err.value)
