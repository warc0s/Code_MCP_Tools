from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import httpx

import app as app_mod
from app import AppState, create_web_app
from mcp_server.toolset import RAGToolset
from utils.config import AppConfig


async def _post_restart(tmp_path: Path) -> httpx.Response:
    config = AppConfig.from_dict(
        {
            "database": {"path": str(tmp_path / "missing.duckdb")},
            "memory_database": {"path": str(tmp_path / "memory.sqlite3")},
        }
    )
    toolset = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    state = AppState(
        config=config,
        toolset=toolset,
        retriever=None,
        connection=None,
        item_service=None,
        lock=asyncio.Lock(),
    )
    executor = state.executor
    try:
        web_app = create_web_app(state, base_path="/mcp")
        transport = httpx.ASGITransport(app=web_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/ui/api/restart")
    finally:
        try:
            executor.shutdown(wait=True, cancel_futures=True)
        except Exception:
            pass


def test_restart_requires_container_name(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTAINER_NAME", raising=False)
    resp = asyncio.run(_post_restart(tmp_path))
    assert resp.status_code == 400


def test_restart_success_uses_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAINER_NAME", "contextarium-tools")
    monkeypatch.setenv("DOCKER_RESTART_TIMEOUT_SEC", "7.5")

    captured = {}

    def _fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(app_mod.subprocess, "run", _fake_run)

    resp = asyncio.run(_post_restart(tmp_path))
    assert resp.status_code == 200, resp.text
    assert resp.json().get("status") == "restarting"
    assert captured["args"] == ["docker", "restart", "contextarium-tools"]
    assert captured["kwargs"].get("timeout") == 7.5


def test_restart_timeout_returns_504(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAINER_NAME", "contextarium-tools")
    monkeypatch.setenv("DOCKER_RESTART_TIMEOUT_SEC", "0.1")

    def _fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout"), output="out", stderr="err")

    monkeypatch.setattr(app_mod.subprocess, "run", _fake_run)

    resp = asyncio.run(_post_restart(tmp_path))
    assert resp.status_code == 504


def test_restart_failure_includes_stderr(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAINER_NAME", "contextarium-tools")
    monkeypatch.delenv("DOCKER_RESTART_TIMEOUT_SEC", raising=False)

    def _fake_run(args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=args, output="out", stderr="boom")

    monkeypatch.setattr(app_mod.subprocess, "run", _fake_run)

    resp = asyncio.run(_post_restart(tmp_path))
    assert resp.status_code == 500
    assert "boom" in (resp.json().get("detail") or "")
