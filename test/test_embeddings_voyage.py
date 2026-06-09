from __future__ import annotations

import pytest

from utils.config import EmbeddingConfig
from utils.embeddings import EmbeddingProvider, VOYAGE_4_NANO_MODEL


class _FakeVoyageSentenceTransformer:
    instances = []

    def __init__(self, model_name, device=None, **kwargs):
        self.model_name = model_name
        self.device = device
        self.kwargs = kwargs
        self.calls = []
        _FakeVoyageSentenceTransformer.instances.append(self)

    def get_sentence_embedding_dimension(self):
        return self.kwargs.get("truncate_dim")

    def encode_document(self, texts, **kwargs):
        self.calls.append(("document", list(texts), dict(kwargs)))
        dim = self.kwargs["truncate_dim"]
        return [[float(i + 1)] * dim for i, _text in enumerate(texts)]

    def encode_query(self, query, **kwargs):
        self.calls.append(("query", query, dict(kwargs)))
        return [0.5] * self.kwargs["truncate_dim"]


def _use_fake_voyage(monkeypatch):
    _FakeVoyageSentenceTransformer.instances = []
    monkeypatch.setattr(
        "utils.embeddings.EmbeddingProvider._load_sentence_transformer",
        lambda self: _FakeVoyageSentenceTransformer,
    )


def test_voyage_4_nano_uses_remote_code_truncate_dim_and_role_encoders(monkeypatch):
    _use_fake_voyage(monkeypatch)
    provider = EmbeddingProvider(
        EmbeddingConfig(model_name=VOYAGE_4_NANO_MODEL),
        mode="local",
    )

    docs = provider.embed_documents(["first doc", "second doc"])
    query = provider.embed_query("find docs")

    model = _FakeVoyageSentenceTransformer.instances[-1]
    assert model.kwargs == {"trust_remote_code": True, "truncate_dim": 1024}
    assert provider.embedding_dim == 1024
    assert len(docs) == 2
    assert len(docs[0]) == 1024
    assert len(query) == 1024
    assert model.calls[0] == (
        "document",
        ["first doc", "second doc"],
        {"normalize_embeddings": True, "convert_to_numpy": True},
    )
    assert model.calls[1] == (
        "query",
        "find docs",
        {"normalize_embeddings": True, "convert_to_numpy": True},
    )


def test_voyage_4_nano_accepts_supported_custom_embedding_dim(monkeypatch):
    _use_fake_voyage(monkeypatch)
    provider = EmbeddingProvider(
        EmbeddingConfig(model_name=VOYAGE_4_NANO_MODEL, embedding_dim=512),
        mode="local",
    )

    provider._ensure_model_loaded()

    model = _FakeVoyageSentenceTransformer.instances[-1]
    assert model.kwargs["truncate_dim"] == 512
    assert provider.embedding_dim == 512


def test_voyage_4_nano_rejects_unsupported_embedding_dim(monkeypatch):
    _use_fake_voyage(monkeypatch)
    provider = EmbeddingProvider(
        EmbeddingConfig(model_name=VOYAGE_4_NANO_MODEL, embedding_dim=999),
        mode="local",
    )

    with pytest.raises(ValueError) as exc_info:
        provider._ensure_model_loaded()

    message = str(exc_info.value)
    assert "voyage-4-nano" in message
    assert "2048" in message
    assert "256" in message
