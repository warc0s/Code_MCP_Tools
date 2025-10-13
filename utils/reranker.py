"""
Wrapper del reranker Qwen/Qwen3-Reranker-0.6B.
"""

from __future__ import annotations

from typing import Iterable, List

from utils.cache import configure_model_cache
from utils.config import RerankerConfig


class PassageReranker:
    def __init__(self, config: RerankerConfig):
        self.config = config
        self._model = None
        self._tokenizer = None
        self._prefix_tokens = None
        self._suffix_tokens = None
        self._task = "Given a web search query, retrieve relevant passages that answer the query"

    def _ensure_model(self) -> None:
        if self._model is not None:
            return

        configure_model_cache()

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - depende de instalación opcional
            raise RuntimeError(
                "transformers/torch no están instalados. Instala los paquetes requeridos para usar el reranker."
            ) from exc

        tokenizer_kwargs = {"padding_side": "left"}
        self._tokenizer = AutoTokenizer.from_pretrained(self.config.model_name, **tokenizer_kwargs)

        self._model = AutoModelForCausalLM.from_pretrained(self.config.model_name).eval()
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

    def rerank(self, query: str, candidates: Iterable[dict], top_k: int) -> List[dict]:
        items = list(candidates)
        if not items:
            return items
        self._ensure_model()
        texts = [item["text"] for item in items[:top_k]]
        inputs = self._build_inputs(query, texts)
        scores = self._compute_scores(inputs)
        for item, score in zip(items[:top_k], scores):
            item["rerank_score"] = score
        return sorted(items, key=lambda it: it.get("rerank_score", it["score"]), reverse=True)


__all__ = ["PassageReranker"]
