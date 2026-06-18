from pathlib import Path

import yaml

from utils.config import AppConfig
from utils.crawling import is_probably_blocked_markdown, normalize_url_for_dedupe


def test_normalize_url_for_dedupe_strips_fragment_only():
    url = "https://example.com/docs/page?a=1#section-2"
    assert normalize_url_for_dedupe(url) == "https://example.com/docs/page?a=1"


def test_is_probably_blocked_markdown_flags_empty_and_captcha():
    assert is_probably_blocked_markdown("") is True
    assert is_probably_blocked_markdown("   ") is True
    assert is_probably_blocked_markdown("Access denied") is True
    assert is_probably_blocked_markdown("Sorry, we just need to make sure you're not a robot") is True


def test_is_probably_blocked_markdown_allows_normal_content():
    md = "# Welcome\n\nThis is documentation content with headings and examples."
    assert is_probably_blocked_markdown(md) is False


def test_config_load_accepts_new_crawling_fields(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    payload = {
        "main": {"mode": "local"},
        "database": {"path": str(tmp_path / "rag.duckdb")},
        "memory_database": {"path": str(tmp_path / "memory.sqlite3")},
        "crawling": {
            "workers": 3,
            "cache_mode": "disabled",
            "text_mode": False,
            "enable_stealth": True,
            "excluded_tags": ["nav", "footer"],
            "word_count_threshold": 1,
            "pruning_threshold": 0.2,
            "pruning_min_word_threshold": 5,
            "min_markdown_chars": 50,
        },
    }
    config_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    cfg = AppConfig.load(config_path)
    assert cfg.crawling.workers == 3
    assert cfg.crawling.cache_mode == "disabled"
    assert cfg.crawling.text_mode is False
    assert cfg.crawling.enable_stealth is True
    assert cfg.crawling.excluded_tags == ["nav", "footer"]
    assert cfg.crawling.word_count_threshold == 1
    assert cfg.crawling.pruning_threshold == 0.2
    assert cfg.crawling.pruning_min_word_threshold == 5
    assert cfg.crawling.min_markdown_chars == 50


def test_crawling_user_agent_default_is_safe_none():
    # Regression: Crawl4AI BrowserConfig crashes if user_agent=None is passed explicitly.
    cfg = AppConfig.from_dict({"crawling": {"user_agent": None}})
    assert cfg.crawling.user_agent is None
