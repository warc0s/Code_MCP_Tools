"""
Utilidades para configurar rutas de caché local de modelos.
"""

from __future__ import annotations

import os
from pathlib import Path
_CACHE_INITIALIZED = False


def configure_model_cache(directory: Path | str = Path(".cache/models")) -> Path:
    """
    Configura las variables de entorno para que HuggingFace y SentenceTransformers
    utilicen un directorio de caché local dentro del proyecto.
    """
    global _CACHE_INITIALIZED

    cache_dir = Path(directory)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not _CACHE_INITIALIZED:
        resolved = str(cache_dir.resolve())
        os.environ.setdefault("HF_HOME", resolved)
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", resolved)
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", resolved)
        _CACHE_INITIALIZED = True

    return cache_dir


__all__ = ["configure_model_cache"]
