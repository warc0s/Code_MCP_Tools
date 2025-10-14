"""
Wrapper del proveedor de embeddings con soporte para ejecución local o en OpenAI.
"""

from __future__ import annotations

import math
import os
from typing import Iterable, List, Optional

from utils.cache import configure_model_cache
from utils.config import EmbeddingConfig
from utils.env import load_env_file

DEFAULT_CLOUD_EMBED_MODEL = "text-embedding-3-small"


class EmbeddingProvider:
    def __init__(self, config: EmbeddingConfig, mode: str = "local"):
        normalized_mode = (mode or "local").strip().lower()
        if normalized_mode not in {"local", "cloud"}:
            raise ValueError("El modo de embeddings debe ser 'local' o 'cloud'.")
        self.mode = normalized_mode

        self.config = config
        self.model_name = (
            config.model_name if self.mode == "local" else config.cloud_model_name or DEFAULT_CLOUD_EMBED_MODEL
        )
        self._model = None
        self._client = None
        self._embedding_dim: Optional[int] = config.embedding_dim

    def _load_sentence_transformer(self):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer

    @property
    def embedding_dim(self) -> int:
        if self._embedding_dim is None:
            if self.mode == "local":
                self._ensure_model_loaded()
            else:
                raise RuntimeError(
                    "No se pudo determinar la dimensión de embeddings para el modo cloud aún. "
                    "Genera embeddings primero o configura 'embedding_dim' explícitamente."
                )
        assert self._embedding_dim is not None
        return self._embedding_dim

    def _ensure_model_loaded(self) -> None:
        if self.mode == "cloud":
            return
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
            self._model = SentenceTransformer(self.model_name)
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo cargar el modelo de embeddings '{self.model_name}': {exc}"
            ) from exc

        self._embedding_dim = int(self._model.get_sentence_embedding_dimension())

    def _ensure_cloud_client(self):
        if self._client is not None:
            return

        load_env_file()
        api_key = os.getenv("openai_api_key") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Falta la variable openai_api_key (o OPENAI_API_KEY) para operar en modo cloud.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "El paquete 'openai' es obligatorio para usar el modo cloud. Añádelo a requirements.txt."
            ) from exc

        self._client = OpenAI(api_key=api_key)

    def _normalize_vector(self, vector: List[float]) -> List[float]:
        if not self.config.normalize_embeddings:
            return vector
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0:
            return vector
        return [component / norm for component in vector]

    def _cloud_embed(self, inputs: List[str]) -> List[List[float]]:
        self._ensure_cloud_client()
        assert self._client is not None

        try:
            response = self._client.embeddings.create(
                model=self.model_name,
                input=inputs,
                encoding_format="float",
            )
        except Exception as exc:
            raise RuntimeError(f"No fue posible generar embeddings en OpenAI: {exc}") from exc

        vectors: List[List[float]] = []
        for item in response.data:
            vector = list(item.embedding)
            vectors.append(self._normalize_vector(vector))

        if vectors and self._embedding_dim is None:
            self._embedding_dim = len(vectors[0])
        return vectors

    def embed_documents(self, texts: Iterable[str]) -> List[List[float]]:
        payload = list(texts)
        if not payload:
            return []
        if self.mode == "local":
            self._ensure_model_loaded()
            vectors = self._model.encode(
                payload,
                normalize_embeddings=self.config.normalize_embeddings,
                convert_to_numpy=True,
            )
            return vectors.tolist()
        return self._cloud_embed(payload)

    def embed_query(self, query: str) -> List[float]:
        if self.mode == "local":
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

        vectors = self._cloud_embed([query])
        return vectors[0] if vectors else []


__all__ = ["DEFAULT_CLOUD_EMBED_MODEL", "EmbeddingProvider"]
