from __future__ import annotations

from utils.config import AppConfig


def test_app_config_no_longer_exposes_policy_section() -> None:
    cfg = AppConfig.from_dict({})
    assert not hasattr(cfg, "policy")


def test_legacy_policy_section_is_ignored() -> None:
    cfg = AppConfig.from_dict({"policy": {"force_english_queries": False}})
    assert cfg.retrieval.force_english_queries is True

