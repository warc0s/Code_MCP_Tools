"""
Reranker wrapper with local and DeepInfra support.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, List

from utils.cache import configure_model_cache
from utils.config import RerankerConfig
from utils.env import load_env_file

CLOUD_RERANKER_MODEL = "Qwen/Qwen3-Reranker-8B"
DEEPINFRA_RERANKER_BASE_URL = "https://api.deepinfra.com/v1/inference/"


def _redact_secrets(message: object, secrets: Iterable[str] = ()) -> str:
    text = str(message)
    for secret in secrets:
        if secret:
            text = text.replace(str(secret), "[REDACTED]")
    return re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "bearer [REDACTED]", text)


class PassageReranker:
    def __init__(self, config: RerankerConfig, mode: str = "local"):
        normalized_mode = (mode or "local").strip().lower()
        if normalized_mode not in {"local", "cloud"}:
            raise ValueError("Reranker mode must be 'local' or 'cloud'.")
        self.mode = normalized_mode

        self.config = config
        self.model_name = (
            config.model_name if self.mode == "local" else config.cloud_model_name or CLOUD_RERANKER_MODEL
        )

        self._model = None
        self._tokenizer = None
        self._prefix_tokens = None
        self._suffix_tokens = None
        self._cloud_token: str | None = None
        self._task = "Given a web search query, retrieve relevant passages that answer the query"

    def _ensure_model(self) -> None:
        if self.mode == "cloud":
            return
        if self._model is not None:
            return

        configure_model_cache()

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - depends on optional installation
            raise RuntimeError(
                "transformers/torch are not installed. Install the required packages to use the reranker."
            ) from exc

        tokenizer_kwargs = {"padding_side": "left"}
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, **tokenizer_kwargs)

        self._model = AutoModelForCausalLM.from_pretrained(self.model_name).eval()
        self._model.to(torch.device("cpu"))

        prefix = (
            "<|im_start|>system\n"
            "Judge whether the Document meets the requirements based on the Query and the Instruct provided. "
            "Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n"
        )
        suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
        self._prefix_tokens = self._tokenizer.encode(prefix, add_special_tokens=False)
        self._suffix_tokens = self._tokenizer.encode(suffix, add_special_tokens=False)
        self._token_true_id = self._tokenizer.convert_tokens_to_ids("yes")
        self._token_false_id = self._tokenizer.convert_tokens_to_ids("no")
        self._max_length = self.config.max_length

    def _format_instruction(self, query: str, document: str) -> str:
        return (
            f"<Instruct>: {self._task}\n<Query>: {query}\n<Document>: {document}"
        )

    def _build_inputs(self, query: str, passages: List[str]):
        import torch

        pairs = [self._format_instruction(query, passage) for passage in passages]
        inputs = self._tokenizer(
            pairs,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=self._max_length - len(self._prefix_tokens) - len(self._suffix_tokens),
        )
        for i, ids in enumerate(inputs["input_ids"]):
            inputs["input_ids"][i] = self._prefix_tokens + ids + self._suffix_tokens
        inputs = self._tokenizer.pad(inputs, padding=True, return_tensors="pt", max_length=self._max_length)
        return {key: value.to(self._model.device) for key, value in inputs.items()}

    def _compute_scores(self, inputs) -> List[float]:
        import torch

        with torch.no_grad():
            logits = self._model(**inputs).logits[:, -1, :]
            true_vector = logits[:, self._token_true_id]
            false_vector = logits[:, self._token_false_id]
            batch_scores = torch.stack([false_vector, true_vector], dim=1)
            probs = torch.nn.functional.log_softmax(batch_scores, dim=1).exp()
            return probs[:, 1].tolist()

    def _ensure_cloud_token(self) -> str:
        if self._cloud_token:
            return self._cloud_token
        load_env_file()
        token = os.getenv("DEEPINFRA_API_KEY")
        if not token:
            raise RuntimeError("Missing DEEPINFRA_API_KEY for cloud reranker mode.")
        self._cloud_token = token
        return token

    def _rerank_cloud(self, query: str, candidates: List[dict], top_k: int) -> List[dict]:
        size = min(top_k, len(candidates))
        if size <= 0:
            return candidates

        documents = [item["text"] for item in candidates[:size]]
        payload = {
            "queries": [query] * size,
            "documents": documents,
        }

        try:
            import requests
        except ImportError as exc:
            raise RuntimeError(
                "The 'requests' package is required for cloud reranker mode."
            ) from exc

        token = self._ensure_cloud_token()
        headers = {
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
        }
        url = f"{DEEPINFRA_RERANKER_BASE_URL}{self.model_name}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
        except requests.RequestException as exc:
            detail = _redact_secrets(exc, [token])
            raise RuntimeError(f"DeepInfra reranker request failed: {detail}") from exc

        if response.status_code >= 400:
            detail = _redact_secrets(response.text, [token])
            raise RuntimeError(
                f"DeepInfra returned reranker error {response.status_code}: {detail}"
            )

        data = response.json()
        scores = data.get("scores")
        if not isinstance(scores, list) or len(scores) != size:
            raise RuntimeError("Unexpected response from cloud reranker.")

        for item, score in zip(candidates[:size], scores):
            item["rerank_score"] = float(score)
        return sorted(candidates, key=lambda it: it.get("rerank_score", it["score"]), reverse=True)

    def rerank(self, query: str, candidates: Iterable[dict], top_k: int) -> List[dict]:
        items = list(candidates)
        if not items:
            return items
        if self.mode == "cloud":
            return self._rerank_cloud(query, items, top_k)

        self._ensure_model()
        texts = [item["text"] for item in items[:top_k]]
        inputs = self._build_inputs(query, texts)
        scores = self._compute_scores(inputs)
        for item, score in zip(items[:top_k], scores):
            item["rerank_score"] = score
        return sorted(items, key=lambda it: it.get("rerank_score", it["score"]), reverse=True)


__all__ = ["CLOUD_RERANKER_MODEL", "PassageReranker"]
