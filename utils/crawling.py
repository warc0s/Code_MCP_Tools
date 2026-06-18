"""
Crawl4AI-based crawler that supplies structured markdown to the RAG pipeline.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence
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

MAX_CRAWLING_WORKERS = 16


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
            return title.replace("\u00b6", "").strip()
    match = re.search(r"^\s*#\s+(.+)$", markdown, flags=re.MULTILINE)
    if match:
        return match.group(1).replace("\u00b6", "").strip()
    path = urlparse(url).path.rstrip("/").split("/")[-1] or urlparse(url).path.strip("/")
    return (path or url).replace("\u00b6", "").strip()


def normalize_url_for_dedupe(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    # Avoid collapsing distinct pages by querystring; strip only fragments.
    if "#" in cleaned:
        cleaned = cleaned.split("#", 1)[0]
    return cleaned


def is_probably_blocked_markdown(markdown: str) -> bool:
    text = (markdown or "").strip().lower()
    if not text:
        return True
    patterns = [
        "sorry, we just need to make sure you're not a robot",
        "robot check",
        "captcha",
        "access denied",
        "request blocked",
        "temporarily unavailable",
        "enable cookies",
        "please enable cookies",
        "unusual traffic",
        "to continue, please",
        "we can't process your request right now",
    ]
    return any(p in text for p in patterns)

def _is_playwright_stealth_import_error(exc: ImportError) -> bool:
    msg = str(exc)
    return ("playwright_stealth" in msg) or ("cannot import name 'Stealth'" in msg) or ("Did you mean: 'stealth'" in msg)


def _safe_worker_count(config: CrawlingConfig) -> int:
    raw_value = getattr(config, "workers", 1)
    try:
        workers = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("crawling.workers must be an integer.") from exc
    return max(1, min(workers, MAX_CRAWLING_WORKERS))


async def discover_urls_from_sitemap(
    sitemap_input: str, config: CrawlingConfig
) -> List[Dict]:
    domain = derive_domain_from_sitemap(sitemap_input)
    workers = _safe_worker_count(config)
    seeding_conf = SeedingConfig(
        source="sitemap",
        extract_head=True,
        pattern=config.pattern,
        max_urls=config.max_urls,
        concurrency=workers * 2,
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
    workers = _safe_worker_count(config)

    def _build_markdown_generator(pruning_enabled: bool) -> DefaultMarkdownGenerator:
        content_filter = None
        if pruning_enabled:
            content_filter = PruningContentFilter(
                threshold=float(getattr(config, "pruning_threshold", 0.5)),
                threshold_type="dynamic",
                min_word_threshold=int(getattr(config, "pruning_min_word_threshold", 15)),
            )
        return DefaultMarkdownGenerator(
            content_filter=content_filter,
            options={
                "ignore_images": True,
                "skip_internal_links": True,
                "body_width": 0,
            },
        )

    def _build_run_config(aggressive: bool) -> CrawlerRunConfig:
        cache = CacheMode.ENABLED if config.cache_mode.lower() == "enabled" else CacheMode.DISABLED
        if not aggressive:
            return CrawlerRunConfig(
                markdown_generator=_build_markdown_generator(pruning_enabled=True),
                excluded_tags=list(getattr(config, "excluded_tags", ["nav", "footer", "aside", "form"])),
                word_count_threshold=int(getattr(config, "word_count_threshold", 5)),
                cache_mode=cache,
                stream=True,
                verbose=False,
                semaphore_count=workers,
                wait_until="domcontentloaded",
                delay_before_return_html=0.2,
            )
        # Aggressive pass: keep more content and wait longer for dynamic pages.
        return CrawlerRunConfig(
            markdown_generator=_build_markdown_generator(pruning_enabled=False),
            excluded_tags=[],
            word_count_threshold=1,
            cache_mode=cache,
            stream=True,
            verbose=False,
            semaphore_count=max(1, min(workers, 4)),
            wait_until="networkidle",
            page_timeout=90000,
            wait_for="main",
            wait_for_timeout=15000,
            delay_before_return_html=1.0,
            remove_overlay_elements=True,
            simulate_user=True,
            scan_full_page=True,
            scroll_delay=0.25,
            max_scroll_steps=16,
        )

    run_config = _build_run_config(aggressive=False)
    base_browser_kwargs: dict = {
        "headless": True,
        "text_mode": bool(getattr(config, "text_mode", True)),
        "verbose": False,
    }
    user_agent = getattr(config, "user_agent", None)
    user_agent_str = user_agent.strip() if isinstance(user_agent, str) and user_agent.strip() else None

    def _build_browser_conf(enable_stealth: bool) -> BrowserConfig:
        kwargs = dict(base_browser_kwargs)
        kwargs["enable_stealth"] = bool(enable_stealth)
        if user_agent_str:
            kwargs["user_agent"] = user_agent_str
        return BrowserConfig(**kwargs)

    browser_conf = _build_browser_conf(bool(getattr(config, "enable_stealth", False)))
    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=85.0,
        check_interval=1.0,
        max_session_permit=workers,
    )
    urls = [e["url"] for e in url_entries]
    results: List[CrawledDocument] = []
    failures: list[dict] = []
    succeeded: set[str] = set()
    min_chars = int(getattr(config, "min_markdown_chars", 200))

    async def _crawl_once(conf: BrowserConfig, batch_urls: list[str], run_cfg: CrawlerRunConfig, label: str) -> None:
        async with AsyncWebCrawler(config=conf) as crawler:
            results_iter = await crawler.arun_many(
                urls=batch_urls,
                config=run_cfg,
                dispatcher=dispatcher,
            )
            with tqdm(total=len(batch_urls), desc=f"Crawling{label}", unit="page") as progress:
                async for result in results_iter:
                    if not result:
                        failures.append({"url": None, "reason": "empty_result"})
                        progress.update(1)
                        continue

                    url = getattr(result, "url", None)
                    if isinstance(url, str) and url in succeeded:
                        # Already captured successfully in a previous pass; skip bookkeeping.
                        progress.update(1)
                        continue
                    if not getattr(result, "success", False):
                        failures.append(
                            {
                                "url": url,
                                "reason": "crawl_failed",
                                "error": str(getattr(result, "error_message", "") or ""),
                                "status_code": getattr(result, "status_code", None),
                            }
                        )
                        progress.update(1)
                        continue

                    if isinstance(result.markdown, str):
                        markdown = result.markdown
                    elif result.markdown:
                        fit = getattr(result.markdown, "fit_markdown", None)
                        markdown = (
                            fit
                            if isinstance(fit, str) and fit.strip()
                            else getattr(result.markdown, "raw_markdown", "") or ""
                        )
                    else:
                        markdown = ""

                    if is_probably_blocked_markdown(markdown):
                        failures.append({"url": url, "reason": "blocked_or_empty"})
                        progress.update(1)
                        continue

                    if len(markdown.strip()) < min_chars:
                        failures.append({"url": url, "reason": "too_short_markdown", "chars": len(markdown.strip())})
                        progress.update(1)
                        continue

                    title = pick_title(url or "", markdown, getattr(result, "metadata", None))
                    fingerprint = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
                    results.append(
                        CrawledDocument(
                            url=url or "",
                            title=title,
                            markdown=markdown,
                            fingerprint=fingerprint,
                        )
                    )
                    if isinstance(url, str) and url:
                        succeeded.add(url)
                    progress.update(1)

    def _retry_urls_for_failures() -> list[str]:
        retry_reasons = {"too_short_markdown", "blocked_or_empty"}
        retry_urls: list[str] = []
        seen = set()
        for f in failures:
            url = f.get("url")
            if not url or f.get("reason") not in retry_reasons:
                continue
            if url in seen:
                continue
            seen.add(url)
            retry_urls.append(url)
        return retry_urls

    try:
        await _crawl_once(browser_conf, urls, run_config, label="")
    except ImportError as exc:
        if bool(getattr(config, "enable_stealth", False)) and _is_playwright_stealth_import_error(exc):
            # The installed playwright_stealth version is incompatible; retry without stealth.
            print("WARN: Crawl4AI stealth is unavailable (playwright_stealth import error). Retrying without stealth.")
            await _crawl_once(_build_browser_conf(False), urls, run_config, label="")
        else:
            raise

    # If many pages are short/blocked, retry those URLs with a more aggressive run config.
    retry_urls = _retry_urls_for_failures()
    if retry_urls:
        print(f"Retrying {len(retry_urls)} URL(s) with aggressive crawl settings...")
        # Keep previous failures but allow successful retry results to be added.
        try:
            await _crawl_once(browser_conf, retry_urls, _build_run_config(aggressive=True), label=" (retry)")
        except ImportError as exc:
            if bool(getattr(config, "enable_stealth", False)) and _is_playwright_stealth_import_error(exc):
                print("WARN: Crawl4AI stealth is unavailable during retry. Retrying without stealth.")
                await _crawl_once(_build_browser_conf(False), retry_urls, _build_run_config(aggressive=True), label=" (retry)")
            else:
                raise

    deduped_by_url: dict[str, CrawledDocument] = {}
    for doc in results:
        key = normalize_url_for_dedupe(doc.url)
        if not key:
            continue
        existing = deduped_by_url.get(key)
        if not existing or len(doc.markdown) > len(existing.markdown):
            deduped_by_url[key] = doc

    ordered = sorted(deduped_by_url.values(), key=lambda d: (slugify(d.title), d.url))
    if failures:
        filtered_failures = [
            f for f in failures if not (isinstance(f.get("url"), str) and f.get("url") in succeeded)
        ]
        # Keep logs concise: show the first few failures and a summary.
        summary: dict[str, int] = {}
        for f in filtered_failures:
            reason = str(f.get("reason") or "unknown")
            summary[reason] = summary.get(reason, 0) + 1
        print(f"Crawl failures summary: {summary}")
        for f in filtered_failures[:8]:
            print(f"- {f.get('reason')}: {f.get('url')}")
    return ordered


async def crawl_sitemap_async(sitemap_url: str, config: CrawlingConfig) -> List[CrawledDocument]:
    url_entries = await discover_urls_from_sitemap(sitemap_url, config)
    if not url_entries:
        raise RuntimeError("No valid URLs were found in the sitemap.")
    return await crawl_urls_to_markdown(url_entries, config)


def crawl_sitemap(sitemap_url: str, config: CrawlingConfig) -> List[CrawledDocument]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        raise RuntimeError("crawl_sitemap must run from a synchronous context.")
    return asyncio.run(crawl_sitemap_async(sitemap_url, config))


async def crawl_url_list_async(urls: Sequence[str], config: CrawlingConfig) -> List[CrawledDocument]:
    cleaned_entries: List[Dict[str, str]] = []
    for raw in urls:
        candidate = (raw or "").strip()
        if not candidate:
            continue
        if re.search(
            r"\.(jpg|jpeg|png|gif|webp|svg|ico|pdf|zip|tar|gz|rar|7z|mp4|mp3|wav|avi|mov|xml)$",
            candidate,
            flags=re.I,
        ):
            continue
        cleaned_entries.append({"url": candidate})
    if not cleaned_entries:
        raise RuntimeError("The URL list does not contain valid entries.")
    return await crawl_urls_to_markdown(cleaned_entries, config)


def crawl_url_list(urls: Sequence[str], config: CrawlingConfig) -> List[CrawledDocument]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        raise RuntimeError("crawl_url_list must run from a synchronous context.")
    return asyncio.run(crawl_url_list_async(list(urls), config))


__all__ = [
    "CrawledDocument",
    "crawl_sitemap",
    "crawl_sitemap_async",
    "crawl_url_list",
    "crawl_url_list_async",
    "discover_urls_from_sitemap",
    "is_probably_blocked_markdown",
    "normalize_url_for_dedupe",
]
