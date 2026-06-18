from __future__ import annotations

import pytest
import requests

from utils.config import RerankerConfig
from utils.reranker import PassageReranker


def test_cloud_reranker_redacts_token_from_request_errors(monkeypatch) -> None:
    token = "deepinfra-secret-token"
    monkeypatch.setenv("DEEPINFRA_API_KEY", token)

    def fail_post(*_args, **_kwargs):
        raise requests.RequestException(f"failed with bearer {token}")

    monkeypatch.setattr(requests, "post", fail_post)
    reranker = PassageReranker(RerankerConfig(cloud_model_name="fake/model"), mode="cloud")

    with pytest.raises(RuntimeError) as exc_info:
        reranker.rerank("query", [{"text": "passage", "score": 0.5}], top_k=1)

    message = str(exc_info.value)
    assert token not in message
    assert "bearer [REDACTED]" in message
