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
DEFAULT_LOCAL_EMBED_MODEL = "voyageai/voyage-4-nano"
VOYAGE_4_NANO_MODEL = "voyageai/voyage-4-nano"
VOYAGE_4_NANO_DEFAULT_DIM = 1024
VOYAGE_4_NANO_SUPPORTED_DIMS = {2048, 1024, 512, 256}
DEFAULT_OPENAI_TIMEOUT_SEC = 45.0
DEFAULT_OPENAI_MAX_RETRIES = 2


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


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
        self._device: Optional[str] = None  # 'cuda' si disponible; 'cpu' en otro caso
        self._local_truncate_dim: Optional[int] = None

    def _load_sentence_transformer(self):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer

    def _is_voyage_4_nano(self) -> bool:
        return self.mode == "local" and self.model_name.strip().lower() == VOYAGE_4_NANO_MODEL

    def _resolve_voyage_truncate_dim(self) -> int:
        requested_dim = self.config.embedding_dim or VOYAGE_4_NANO_DEFAULT_DIM
        if requested_dim not in VOYAGE_4_NANO_SUPPORTED_DIMS:
            allowed = ", ".join(str(dim) for dim in sorted(VOYAGE_4_NANO_SUPPORTED_DIMS, reverse=True))
            raise ValueError(
                f"voyage-4-nano only supports embedding_dim values: {allowed}."
            )
        return int(requested_dim)

    def _sentence_transformer_kwargs(self) -> dict:
        if not self._is_voyage_4_nano():
            return {}
        self._local_truncate_dim = self._resolve_voyage_truncate_dim()
        return {
            "trust_remote_code": True,
            "truncate_dim": self._local_truncate_dim,
        }

    def _vectors_to_lists(self, vectors) -> List[List[float]]:
        if hasattr(vectors, "tolist"):
            vectors = vectors.tolist()
        if not isinstance(vectors, list):
            vectors = list(vectors)
        if not vectors:
            return []
        if all(isinstance(value, (int, float)) for value in vectors):
            return [[float(value) for value in vectors]]
        return [[float(value) for value in vector] for vector in vectors]

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
                    "Instala una build CPU de torch (por ejemplo, `pip install --extra-index-url https://download.pytorch.org/whl/cpu torch==2.4.1+cpu`)."
                )
            elif "libnccl.so" in joined or "nccl" in joined:
                hint = (
                    "La build de torch detectada intenta usar NCCL/CUDA y falla. "
                    "Instala la versión CPU: `pip install --upgrade --extra-index-url https://download.pytorch.org/whl/cpu torch==2.4.1+cpu`."
                )
            elif "torchvision::nms" in joined or "torchvision" in joined:
                hint = (
                    "Conflicto con torchvision detectado (mismatch con torch). "
                    "Instala torchvision CPU a juego con tu torch: `pip install --extra-index-url https://download.pytorch.org/whl/cpu torchvision==0.19.1+cpu`."
                )
            elif "could not import module 'pretrainedmodel'" in joined:
                hint = (
                    "Transformers parece roto o desalineado. Reinstala `transformers` y `sentence-transformers`: "
                    "`pip install -U transformers sentence-transformers` y asegúrate de usar Torch/torchvision CPU compatibles."
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

        # Selección de dispositivo: usa CUDA si está disponible, si no CPU.
        device = "cpu"
        try:
            # Preferir un stub inyectado en tests si existe
            import sys as _sys  # type: ignore
            torch_mod = getattr(_sys.modules.get(__name__), "torch", None)
            if torch_mod is None:
                import torch as torch_mod  # type: ignore
            if getattr(torch_mod, "cuda", None) and torch_mod.cuda.is_available():
                device = "cuda"
        except Exception:
            device = "cpu"
        self._device = device

        model_kwargs = self._sentence_transformer_kwargs()
        try:
            self._model = SentenceTransformer(
                self.model_name,
                device=self._device,
                **model_kwargs,
            )
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo cargar el modelo de embeddings '{self.model_name}': {exc}"
            ) from exc

        model_dim = self._model.get_sentence_embedding_dimension()
        if model_dim is None and self._local_truncate_dim is not None:
            model_dim = self._local_truncate_dim
        self._embedding_dim = int(model_dim)

    @property
    def device(self) -> Optional[str]:
        """Devuelve el dispositivo elegido ('cuda' o 'cpu') tras cargar el modelo."""
        return self._device

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

        self._client = OpenAI(
            api_key=api_key,
            timeout=_env_float("OPENAI_TIMEOUT_SEC", DEFAULT_OPENAI_TIMEOUT_SEC),
            max_retries=_env_int("OPENAI_MAX_RETRIES", DEFAULT_OPENAI_MAX_RETRIES),
        )

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
            kwargs = {
                "normalize_embeddings": self.config.normalize_embeddings,
                "convert_to_numpy": True,
            }
            if self._is_voyage_4_nano() and hasattr(self._model, "encode_document"):
                vectors = self._model.encode_document(payload, **kwargs)
            else:
                vectors = self._model.encode(payload, **kwargs)
            return self._vectors_to_lists(vectors)
        return self._cloud_embed(payload)

    def embed_query(self, query: str) -> List[float]:
        if self.mode == "local":
            self._ensure_model_loaded()
            kwargs = {
                "normalize_embeddings": self.config.normalize_embeddings,
                "convert_to_numpy": True,
            }
            if self._is_voyage_4_nano() and hasattr(self._model, "encode_query"):
                vectors = self._model.encode_query(query, **kwargs)
                as_lists = self._vectors_to_lists(vectors)
                return as_lists[0] if as_lists else []

            if self.config.query_prompt_name:
                kwargs["prompt_name"] = self.config.query_prompt_name
            vectors = self._model.encode([query], **kwargs)
            as_lists = self._vectors_to_lists(vectors)
            return as_lists[0] if as_lists else []

        vectors = self._cloud_embed([query])
        return vectors[0] if vectors else []


__all__ = [
    "DEFAULT_CLOUD_EMBED_MODEL",
    "DEFAULT_LOCAL_EMBED_MODEL",
    "DEFAULT_OPENAI_MAX_RETRIES",
    "DEFAULT_OPENAI_TIMEOUT_SEC",
    "EmbeddingProvider",
    "VOYAGE_4_NANO_MODEL",
]
