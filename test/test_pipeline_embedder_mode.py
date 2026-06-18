from __future__ import annotations

from utils.config import AppConfig
from utils.pipeline import IngestionSummary
from utils import pipeline as pipeline_mod


class _FakeEmbedder:
    def __init__(self, _config, mode: str = "local"):
        self.mode = mode


def test_rebuild_rag_from_urls_uses_config_mode(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "EmbeddingProvider", _FakeEmbedder)
    monkeypatch.setattr(pipeline_mod, "crawl_url_list", lambda _urls, _cfg: [])

    def _fake_rebuild(_docs, config, embedder, progress_cb=None):
        assert embedder.mode == config.main.mode
        return IngestionSummary(documents=0, chunks=0)

    monkeypatch.setattr(pipeline_mod, "_rebuild_rag_from_crawled_documents", _fake_rebuild)

    config = AppConfig.from_dict({"main": {"mode": "cloud"}})
    pipeline_mod.rebuild_rag_from_urls(["https://example.com"], config)


def test_rebuild_rag_from_sitemap_uses_config_mode(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "EmbeddingProvider", _FakeEmbedder)
    monkeypatch.setattr(pipeline_mod, "crawl_sitemap", lambda _url, _cfg: [])

    def _fake_rebuild(_docs, config, embedder, progress_cb=None):
        assert embedder.mode == config.main.mode
        return IngestionSummary(documents=0, chunks=0)

    monkeypatch.setattr(pipeline_mod, "_rebuild_rag_from_crawled_documents", _fake_rebuild)

    config = AppConfig.from_dict({"main": {"mode": "cloud"}})
    pipeline_mod.rebuild_rag_from_sitemap("https://example.com/sitemap.xml", config)

