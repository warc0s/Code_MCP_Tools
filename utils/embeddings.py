"""
Wrapper del modelo de embeddings para desacoplar la lógica de SentenceTransformers.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from utils.cache import configure_model_cache
from utils.config import EmbeddingConfig


class EmbeddingProvider:
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._model = None
        self._embedding_dim: Optional[int] = config.embedding_dim

    def _load_sentence_transformer(self):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer

    @property
    def embedding_dim(self) -> int:
        if self._embedding_dim is None:
            self._ensure_model_loaded()
        assert self._embedding_dim is not None
        return self._embedding_dim

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return

        configure_model_cache()

        try:
            SentenceTransformer = self._load_sentence_transformer()
        except ImportError as exc:  # pragma: no cover - se valida en runtime
            message_chain = []
            current = exc
            while current:
                message_chain.append(str(current))
                current = current.__cause__ or current.__context__
            joined = " ".join(message_chain).lower()

            hint = (
                "sentence-transformers no está instalado. Añádelo a requirements.txt e instálalo."
            )
            if "no module named 'torch'" in joined or "requires the following packages" in joined:
                hint = (
                    "sentence-transformers requiere torch para funcionar. "
                    "Instala una build compatible de torch (por ejemplo, `pip install torch`)."
                )
            elif "no module named 'six'" in joined:
                hint = (
                    "sentence-transformers requiere la dependencia `six`. "
                    "Instálala con `pip install six`."
                )
            elif "automodelforsequenceclassification" in joined:
                hint = (
                    "La instalación de transformers está incompleta. Reinstala `transformers` y `torch`."
                )

            raise RuntimeError(f"{hint} Detalle: {message_chain[0]}") from exc

        try:
            self._model = SentenceTransformer(self.config.model_name)
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo cargar el modelo de embeddings '{self.config.model_name}': {exc}"
            ) from exc

        self._embedding_dim = int(self._model.get_sentence_embedding_dimension())

    def embed_documents(self, texts: Iterable[str]) -> List[List[float]]:
        self._ensure_model_loaded()
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=self.config.normalize_embeddings,
            convert_to_numpy=True,
        )
        return vectors.tolist()

    def embed_query(self, query: str) -> List[float]:
        self._ensure_model_loaded()
        kwargs = {}
        if self.config.query_prompt_name:
            kwargs["prompt_name"] = self.config.query_prompt_name
        vector = self._model.encode(
            [query],
            normalize_embeddings=self.config.normalize_embeddings,
            convert_to_numpy=True,
            **kwargs,
        )[0]
        return vector.tolist()


__all__ = ["EmbeddingProvider"]
