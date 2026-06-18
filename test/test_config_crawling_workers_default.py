from pathlib import Path

from utils.config import AppConfig


def test_repo_config_sets_crawling_workers_to_one():
    repo_root = Path(__file__).resolve().parents[1]
    cfg = AppConfig.load(repo_root / "config.yaml")
    assert cfg.crawling.workers == 1


def test_default_crawling_workers_is_one_when_section_missing():
    cfg = AppConfig.from_dict({})
    assert cfg.crawling.workers == 1


def test_repo_config_sets_embeddings_batch_size_to_16():
    repo_root = Path(__file__).resolve().parents[1]
    cfg = AppConfig.load(repo_root / "config.yaml")
    assert cfg.embeddings.batch_size == 16


def test_default_embeddings_batch_size_is_64_when_section_missing():
    cfg = AppConfig.from_dict({})
    assert cfg.embeddings.batch_size == 64
