import pytest
import sys
from pathlib import Path as _Path

# Ensure repository root in sys.path for local imports
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utils.embeddings import EmbeddingProvider
from utils.config import EmbeddingConfig


def test_nccl_missing_produces_cpu_hint(monkeypatch):
    provider = EmbeddingProvider(EmbeddingConfig(), mode="local")

    def fake_loader():
        # Simula un fallo típico al importar torch con build CUDA sin NCCL
        raise ImportError("libnccl.so.2: cannot open shared object file: No such file or directory")

    monkeypatch.setattr(provider, "_load_sentence_transformer", fake_loader)

    with pytest.raises(RuntimeError) as ei:
        provider._ensure_model_loaded()

    msg = str(ei.value).lower()
    assert "cpu" in msg and ("nccl" in msg or "libnccl" in msg)


def test_torchvision_mismatch_hint(monkeypatch):
    provider = EmbeddingProvider(EmbeddingConfig(), mode="local")

    def fake_loader():
        raise ImportError("RuntimeError: operator torchvision::nms does not exist")

    monkeypatch.setattr(provider, "_load_sentence_transformer", fake_loader)

    with pytest.raises(RuntimeError) as ei:
        provider._ensure_model_loaded()

    msg = str(ei.value).lower()
    assert "torchvision" in msg and "cpu" in msg


def test_device_auto_cuda_selection(monkeypatch):
    # Evita descargar modelos reales: stub de SentenceTransformer
    class FakeST:
        def __init__(self, model_name, device=None, **kwargs):
            self.model_name = model_name
            self.device = device
            self.kwargs = kwargs

        def get_sentence_embedding_dimension(self):
            return 10

        def encode(self, texts, **kwargs):
            import numpy as np
            return np.zeros((len(texts), 10), dtype=float)

    provider = EmbeddingProvider(EmbeddingConfig(), mode="local")

    # Forzamos que "haya" CUDA disponible sin importar torch real
    monkeypatch.setattr("utils.embeddings.EmbeddingProvider._load_sentence_transformer", lambda self: FakeST)
    monkeypatch.setattr("utils.embeddings.__builtins__", __builtins__)  # safeguard

    # Parcheamos la verificación a través de un stub simple: simulamos torch cuda available
    class _Cuda:
        @staticmethod
        def is_available():
            return True

    class _TorchStub:
        cuda = _Cuda()

    import utils.embeddings as emb_mod
    emb_mod.torch = _TorchStub()

    provider._ensure_model_loaded()
    assert provider.device == "cuda"
