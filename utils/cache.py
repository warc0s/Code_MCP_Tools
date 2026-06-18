"""
Utilities for configuring local model cache paths.
"""

from __future__ import annotations

import os
from pathlib import Path
_CACHE_INITIALIZED = False


def configure_model_cache(directory: Path | str = Path(".cache/models")) -> Path:
    """
    Configure environment variables so HuggingFace and SentenceTransformers use
    a local cache directory inside the project.
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
