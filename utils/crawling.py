"""
Crawler basado en Crawl4AI que suministra markdown estructurado para el pipeline RAG.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

from tqdm import tqdm

from crawl4ai import (
    AsyncUrlSeeder,
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    SeedingConfig,
)
from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from utils.config import CrawlingConfig


@dataclass
class CrawledDocument:
    url: str
    title: str
    markdown: str
    fingerprint: str


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def derive_domain_from_sitemap(sitemap_url: str) -> str:
    parsed = urlparse(sitemap_url)
    if not parsed.scheme:
        host = sitemap_url.strip().replace("http://", "").replace("https://", "")
        return host.strip("/").split("/")[0]
    return parsed.netloc


def pick_title(url: str, markdown: str, meta: Optional[dict]) -> str:
    if meta and isinstance(meta, dict):
        title = meta.get("title") or meta.get("og:title") or meta.get("twitter:title")
        if title:
            return title.replace("¶", "").strip()
    match = re.search(r"^\s*#\s+(.+)$", markdown, flags=re.MULTILINE)
    if match:
        return match.group(1).replace("¶", "").strip()
    path = urlparse(url).path.rstrip("/").split("/")[-1] or urlparse(url).path.strip("/")
    return (path or url).replace("¶", "").strip()


async def discover_urls_from_sitemap(
    sitemap_input: str, config: CrawlingConfig
) -> List[Dict]:
    domain = derive_domain_from_sitemap(sitemap_input)
    seeding_conf = SeedingConfig(
        source="sitemap",
        extract_head=True,
        pattern=config.pattern,
        max_urls=config.max_urls,
        concurrency=config.workers * 2,
        verbose=False,
        filter_nonsense_urls=True,
        live_check=False,
    )
    async with AsyncUrlSeeder() as seeder:
        urls = await seeder.urls(domain, seeding_conf)
    cleaned = []
    for entry in urls:
        url = entry.get("url") or entry.get("loc") or ""
        if not url:
            continue
        status = entry.get("status", "valid")
        if status != "valid":
            continue
        if re.search(
            r"\.(jpg|jpeg|png|gif|webp|svg|ico|pdf|zip|tar|gz|rar|7z|mp4|mp3|wav|avi|mov|xml)$",
            url,
            flags=re.I,
        ):
            continue
        cleaned.append(entry)
    return cleaned


async def crawl_urls_to_markdown(url_entries: List[Dict], config: CrawlingConfig) -> List[CrawledDocument]:
    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=0.5,
            threshold_type="dynamic",
            min_word_threshold=15,
        ),
        options={
            "ignore_images": True,
            "skip_internal_links": True,
            "body_width": 0,
        },
    )
    run_config = CrawlerRunConfig(
        markdown_generator=md_generator,
        excluded_tags=["nav", "footer", "header", "form", "aside"],
        word_count_threshold=10,
        cache_mode=CacheMode.ENABLED if config.cache_mode.lower() == "enabled" else CacheMode.DISABLED,
        stream=True,
        verbose=False,
        semaphore_count=config.workers,
    )
    browser_conf = BrowserConfig(
        headless=True,
        text_mode=True,
        verbose=False,
    )
    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=85.0,
        check_interval=1.0,
        max_session_permit=config.workers,
    )
    urls = [e["url"] for e in url_entries]
    results: List[CrawledDocument] = []

    async with AsyncWebCrawler(config=browser_conf) as crawler:
        results_iter = await crawler.arun_many(
            urls=urls,
            config=run_config,
            dispatcher=dispatcher,
        )
        with tqdm(total=len(urls), desc="Crawling", unit="page") as progress:
            async for result in results_iter:
                if result and getattr(result, "success", False):
                    if isinstance(result.markdown, str):
                        markdown = result.markdown
                    elif result.markdown:
                        fit = getattr(result.markdown, "fit_markdown", None)
                        markdown = (
                            fit if isinstance(fit, str) and fit.strip() else getattr(result.markdown, "raw_markdown", "") or ""
                        )
                    else:
                        markdown = ""
                    title = pick_title(result.url, markdown, result.metadata)
                    fingerprint = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
                    results.append(
                        CrawledDocument(
                            url=result.url,
                            title=title,
                            markdown=markdown,
                            fingerprint=fingerprint,
                        )
                    )
                progress.update(1)

    deduped = {doc.fingerprint: doc for doc in results}
    ordered = sorted(deduped.values(), key=lambda d: (slugify(d.title), d.url))
    return ordered


async def crawl_sitemap_async(sitemap_url: str, config: CrawlingConfig) -> List[CrawledDocument]:
    url_entries = await discover_urls_from_sitemap(sitemap_url, config)
    if not url_entries:
        raise RuntimeError("No se encontraron URLs válidas en el sitemap.")
    return await crawl_urls_to_markdown(url_entries, config)


def crawl_sitemap(sitemap_url: str, config: CrawlingConfig) -> List[CrawledDocument]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        raise RuntimeError("crawl_sitemap debe ejecutarse desde un contexto síncrono.")
    return asyncio.run(crawl_sitemap_async(sitemap_url, config))


__all__ = ["CrawledDocument", "crawl_sitemap", "crawl_sitemap_async", "discover_urls_from_sitemap"]
