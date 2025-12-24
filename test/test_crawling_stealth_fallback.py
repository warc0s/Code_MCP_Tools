import asyncio

from utils.config import CrawlingConfig
import utils.crawling as crawling


class _FakeResult:
    def __init__(self, url: str, markdown: str, success: bool = True):
        self.url = url
        self.success = success
        self.markdown = markdown
        self.metadata = {"title": "Doc"}


class _FakeAsyncWebCrawler:
    def __init__(self, config):
        self.config = config

    async def __aenter__(self):
        if getattr(self.config, "enable_stealth", False):
            raise ImportError(
                "cannot import name 'Stealth' from 'playwright_stealth' (/x/playwright_stealth/__init__.py). Did you mean: 'stealth'?"
            )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def arun_many(self, urls, config, dispatcher):
        async def _gen():
            for url in urls:
                yield _FakeResult(url=url, markdown="# Title\n\nSome documentation content here.", success=True)

        return _gen()


def test_crawl_falls_back_when_stealth_import_fails(monkeypatch):
    monkeypatch.setattr(crawling, "AsyncWebCrawler", _FakeAsyncWebCrawler)
    config = CrawlingConfig(
        enable_stealth=True,
        text_mode=False,
        cache_mode="disabled",
        min_markdown_chars=10,
        workers=1,
    )
    docs = asyncio.run(crawling.crawl_urls_to_markdown([{"url": "https://example.com"}], config))
    assert len(docs) == 1
    assert docs[0].url == "https://example.com"

