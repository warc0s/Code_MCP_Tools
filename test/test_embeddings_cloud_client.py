from __future__ import annotations

import sys
from types import SimpleNamespace

from utils.config import EmbeddingConfig
from utils.embeddings import EmbeddingProvider


def test_cloud_client_uses_explicit_timeout_and_retries(monkeypatch):
    created = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_TIMEOUT_SEC", "12.5")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "4")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    provider = EmbeddingProvider(
        EmbeddingConfig(cloud_model_name="text-embedding-3-small"),
        mode="cloud",
    )
    provider._ensure_cloud_client()

    assert created == [
        {
            "api_key": "test-key",
            "timeout": 12.5,
            "max_retries": 4,
        }
    ]
