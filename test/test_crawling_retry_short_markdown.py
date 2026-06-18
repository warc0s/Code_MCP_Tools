import asyncio

import utils.crawling as crawling
from utils.config import CrawlingConfig


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
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def arun_many(self, urls, config, dispatcher):
        async def _gen():
            for url in urls:
                # First pass uses word_count_threshold=5 and should be considered too short.
                if getattr(config, "word_count_threshold", None) == 5:
                    yield _FakeResult(url=url, markdown="short", success=True)
                else:
                    yield _FakeResult(url=url, markdown="# Title\n\n" + ("content " * 80), success=True)

        return _gen()


def test_retry_recovers_short_markdown(monkeypatch):
    monkeypatch.setattr(crawling, "AsyncWebCrawler", _FakeAsyncWebCrawler)
    cfg = CrawlingConfig(
        workers=1,
        cache_mode="disabled",
        text_mode=False,
        enable_stealth=False,
        min_markdown_chars=50,
        word_count_threshold=5,
    )
    docs = asyncio.run(crawling.crawl_urls_to_markdown([{"url": "https://example.com/a"}], cfg))
    assert len(docs) == 1
    assert "content" in docs[0].markdown

