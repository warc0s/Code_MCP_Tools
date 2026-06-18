from __future__ import annotations

import pytest
import yaml
from fastapi import HTTPException

from app import AppState, _available_tools_from_config, _persist_enabled_tools, _persist_settings
from mcp_server.toolset import RAGToolset
from utils.config import AppConfig


def _state(config: AppConfig) -> AppState:
    return AppState(
        config=config,
        toolset=RAGToolset(retriever=None, enabled_tools=None),
        retriever=None,
        connection=None,
        item_service=None,
    )


def test_empty_enabled_tools_exposes_no_tools() -> None:
    toolset = RAGToolset(retriever=None, enabled_tools=[])

    assert toolset.list_tools() == {}


def test_tool_sets_with_all_tools_disabled_return_empty_selection() -> None:
    config = AppConfig.from_dict(
        {
            "mcp": {
                "active_set": "locked",
                "tool_sets": {
                    "locked": {
                        "hybrid_search": False,
                        "chunks_by_url": False,
                    }
                },
            }
        }
    )

    assert _available_tools_from_config(config) == []


def test_tool_flags_must_be_booleans() -> None:
    config = AppConfig.from_dict(
        {
            "mcp": {
                "tools": {
                    "hybrid_search": "false",
                }
            }
        }
    )

    with pytest.raises(ValueError, match="booleans"):
        _available_tools_from_config(config)


def test_tool_sets_without_active_set_use_stable_sorted_fallback() -> None:
    config = AppConfig.from_dict(
        {
            "mcp": {
                "tool_sets": {
                    "z-last": {"hybrid_search": True},
                    "a-first": {"chunks_by_url": True},
                }
            }
        }
    )

    assert _available_tools_from_config(config) == ["chunks_by_url"]


def test_persist_enabled_tools_uses_stable_tool_set_fallback(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    original = {
        "mcp": {
            "tool_sets": {
                "z-last": {"hybrid_search": True},
                "a-first": {"chunks_by_url": False},
            }
        }
    }
    config_path.write_text(yaml.safe_dump(original, sort_keys=False), encoding="utf-8")
    state = _state(AppConfig.from_dict(original))
    try:
        _persist_enabled_tools(["chunks_by_url"], state, config_path)

        saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert saved["mcp"]["active_set"] == "a-first"
        assert saved["mcp"]["tool_sets"]["a-first"]["chunks_by_url"] is True
        assert saved["mcp"]["tool_sets"]["z-last"]["hybrid_search"] is True
    finally:
        state.executor.shutdown(wait=True, cancel_futures=True)


def test_persist_enabled_tools_allows_empty_selection(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "mcp": {
                    "tools": {
                        "hybrid_search": True,
                        "chunks_by_url": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    state = _state(AppConfig.from_dict(yaml.safe_load(config_path.read_text(encoding="utf-8"))))
    try:
        _persist_enabled_tools([], state, config_path)

        saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert saved["mcp"]["tools"]
        assert not any(saved["mcp"]["tools"].values())
    finally:
        state.executor.shutdown(wait=True, cancel_futures=True)


def test_persist_enabled_tools_rejects_unknown_tools(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    original = {"mcp": {"tools": {"hybrid_search": True}}}
    config_path.write_text(yaml.safe_dump(original), encoding="utf-8")
    state = _state(AppConfig.from_dict(original))
    try:
        with pytest.raises(HTTPException) as exc_info:
            _persist_enabled_tools(["hybrid_search", "shell_escape"], state, config_path)

        assert exc_info.value.status_code == 400
        assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == original
    finally:
        state.executor.shutdown(wait=True, cancel_futures=True)


def test_persist_settings_rejects_invalid_mode_before_writing(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    original = {
        "main": {"mode": "local"},
        "retrieval": {"enable_rerank": False},
    }
    config_path.write_text(yaml.safe_dump(original), encoding="utf-8")
    state = _state(AppConfig.from_dict(original))
    try:
        with pytest.raises(HTTPException) as exc_info:
            _persist_settings({"mode": "sideways"}, state, config_path)

        assert exc_info.value.status_code == 400
        assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == original
        assert state.config.main.mode == "local"
    finally:
        state.executor.shutdown(wait=True, cancel_futures=True)


def test_persist_settings_rejects_non_boolean_rerank_before_writing(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    original = {
        "main": {"mode": "local"},
        "retrieval": {"enable_rerank": False},
    }
    config_path.write_text(yaml.safe_dump(original), encoding="utf-8")
    state = _state(AppConfig.from_dict(original))
    try:
        with pytest.raises(HTTPException) as exc_info:
            _persist_settings({"enable_rerank": "false"}, state, config_path)

        assert exc_info.value.status_code == 400
        assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == original
        assert state.config.retrieval.enable_rerank is False
    finally:
        state.executor.shutdown(wait=True, cancel_futures=True)
