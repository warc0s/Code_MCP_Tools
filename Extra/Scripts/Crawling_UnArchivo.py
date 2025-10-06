#!/usr/bin/env python3
"""
Crawl un sitemap con Crawl4AI y genera un .md consolidado y limpio.

Requisitos:
  pip install crawl4ai tqdm

Tras instalar, ejecuta una vez:
  crawl4ai-setup
"""

import asyncio
import re
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from tqdm import tqdm

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    AsyncUrlSeeder,
    SeedingConfig,
)
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def derive_domain_from_sitemap(sitemap_url: str) -> str:
    """
    Acepta un dominio o una URL completa al sitemap y devuelve el host.
    """
    parsed = urlparse(sitemap_url)
    if not parsed.scheme:
        host = sitemap_url.strip().replace("http://", "").replace("https://", "")
        return host.strip("/").split("/")[0]
    return parsed.netloc


def pick_title(url: str, markdown: str, meta: Optional[dict]) -> str:
    if meta and isinstance(meta, dict):
        t = meta.get("title") or meta.get("og:title") or meta.get("twitter:title")
        if t:
            return t.replace("¶", "").strip()
    m = re.search(r"^\s*#\s+(.+)$", markdown, flags=re.MULTILINE)
    if m:
        return m.group(1).replace("¶", "").strip()
    path = urlparse(url).path.rstrip("/").split("/")[-1] or urlparse(url).path.strip("/")
    return (path or url).replace("¶", "").strip()


def clean_markdown(markdown: str, compact: bool) -> str:
    if not isinstance(markdown, str):
        return ""
    text = markdown.replace("¶", "")
    if compact:
        # Remove markdown links but keep the visible text
        text = re.sub(r"!\[(.*?)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"(?<!!)\[(.*?)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"\[(.*?)\]\[(.*?)\]", r"\1", text)
        text = re.sub(r"^\s*Skip to content\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render_document(
    domain: str,
    sitemap_url: str,
    items: List[Dict[str, str]],
    out_name: str,
    compact: bool,
) -> Path:
    """
    items: lista de dicts con keys: title, url, md
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append(f"# Documentación consolidada de {domain}")
    lines.append("")
    lines.append(f"> Origen del sitemap: {sitemap_url}")
    lines.append(f"> Generado: {ts}")
    lines.append(f"> Páginas incluidas: {len(items)}")
    lines.append("")
    lines.append("## Índice")
    lines.append("")
    for it in items:
        if compact:
            lines.append(it["title"])
        else:
            anchor = slugify(it["title"])
            lines.append(f"- [{it['title']}](#{anchor})")
    lines.append("")
    for it in items:
        lines.append(f"\n---\n")
        lines.append(f"## {it['title']}")
        lines.append("")
        if not compact:
            lines.append(f"_Fuente_: {it['url']}")
            lines.append("")
        lines.append(clean_markdown(it["md"], compact=compact))
        lines.append("")
    content = "\n".join(lines).strip() + "\n"
    out_path = Path(out_name).with_suffix(".md")
    out_path.write_text(content, encoding="utf-8")
    return out_path


async def discover_urls_from_sitemap(sitemap_input: str, pattern: str = "*", max_urls: int = -1) -> List[Dict]:
    """
    Usa AsyncUrlSeeder para obtener URLs desde el sitemap del dominio dado.
    """
    domain = derive_domain_from_sitemap(sitemap_input)
    seeding_conf = SeedingConfig(
        source="sitemap",
        extract_head=True,
        pattern=pattern,
        max_urls=max_urls,
        concurrency=20,
        verbose=False,
        filter_nonsense_urls=True,
        live_check=False,
    )
    async with AsyncUrlSeeder() as seeder:
        urls = await seeder.urls(domain, seeding_conf)
    cleaned = []
    for u in urls:
        url = u.get("url") or u.get("loc") or ""
        if not url:
            continue
        status = u.get("status", "valid")
        if status != "valid":
            continue
        if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|ico|pdf|zip|tar|gz|rar|7z|mp4|mp3|wav|avi|mov|xml)$", url, flags=re.I):
            continue
        cleaned.append(u)
    return cleaned


async def crawl_urls_to_markdown(url_entries: List[Dict], workers: int = 8) -> List[Dict[str, str]]:
    """
    Devuelve lista de dicts: {title, url, md}
    """
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
        cache_mode=CacheMode.ENABLED,
        stream=True,
        verbose=False,
        semaphore_count=workers,
    )
    browser_conf = BrowserConfig(
        headless=True,
        text_mode=True,
        verbose=False,
    )
    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=85.0,
        check_interval=1.0,
        max_session_permit=workers,
    )
    urls = [e["url"] for e in url_entries]
    results_data: List[Dict[str, str]] = []
    successes = 0
    failures = 0

    async with AsyncWebCrawler(config=browser_conf) as crawler:
        results_iter = await crawler.arun_many(
            urls=urls,
            config=run_config,
            dispatcher=dispatcher,
        )
        with tqdm(total=len(urls), desc="Crawling", unit="page") as pbar:
            async for result in results_iter:
                if result and getattr(result, "success", False):
                    if isinstance(result.markdown, str):
                        md = result.markdown
                    elif result.markdown:
                        fit = getattr(result.markdown, "fit_markdown", None)
                        md = fit if isinstance(fit, str) and fit.strip() else getattr(result.markdown, "raw_markdown", "") or ""
                    else:
                        md = ""
                    title = pick_title(result.url, md, result.metadata)
                    results_data.append({"title": title, "url": result.url, "md": md})
                    successes += 1
                else:
                    failures += 1
                pbar.set_postfix_str(f"ok={successes} fail={failures}")
                pbar.update(1)

    results_data.sort(key=lambda x: (slugify(x["title"]), x["url"]))
    return results_data


async def main():
    print("Hola. Pega la URL de un sitemap o un dominio")
    sitemap_input = input("> ").strip()
    if not sitemap_input:
        print("No se proporcionó entrada. Saliendo.")
        return

    default_name = f"{slugify(derive_domain_from_sitemap(sitemap_input))}-docs-{datetime.now().strftime('%Y%m%d')}"
    print("Nombre del archivo de salida sin extensión .md")
    out_name_in = input(f"[{default_name}]: ").strip()
    out_name = out_name_in or default_name

    compact_answer = input("¿Modo compacto? (s/n) [n]: ").strip().lower()
    compact = compact_answer in {"s", "si", "sí", "y", "yes"}

    print("Descubriendo URLs desde el sitemap. Esto puede tardar si el sitio es grande...")
    url_entries = await discover_urls_from_sitemap(sitemap_input)
    if not url_entries:
        print("No se encontraron URLs válidas.")
        return
    print(f"Encontradas {len(url_entries)} URLs válidas. Iniciando crawling...")

    items = await crawl_urls_to_markdown(url_entries, workers=8)

    out_path = render_document(
        domain=derive_domain_from_sitemap(sitemap_input),
        sitemap_url=sitemap_input,
        items=items,
        out_name=out_name,
        compact=compact,
    )
    print(f"Listo. Escrito: {out_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
