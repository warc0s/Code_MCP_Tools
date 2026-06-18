from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import httpx

import app as app_mod
from app import AppState, create_web_app
from mcp_server.toolset import RAGToolset
from utils.config import AppConfig
from utils.pipeline import IngestionSummary


async def _post(tmp_path: Path, url: str, payload: dict) -> httpx.Response:
    config = AppConfig.from_dict(
        {
            "database": {"path": str(tmp_path / "missing.duckdb")},
            "memory_database": {"path": str(tmp_path / "memory.sqlite3")},
        }
    )
    toolset = RAGToolset(retriever=None, enabled_tools=None)
    state = AppState(
        config=config,
        toolset=toolset,
        retriever=None,
        connection=None,
        item_service=None,
        lock=asyncio.Lock(),
    )
    web_app = create_web_app(state, base_path="/mcp")
    executor = state.executor
    try:
        transport = httpx.ASGITransport(app=web_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(url, json=payload)
    finally:
        try:
            executor.shutdown(wait=True, cancel_futures=True)
        except Exception:
            pass


def test_rebuild_url_file_rejects_traversal(tmp_path):
    resp = asyncio.run(_post(tmp_path, "/ui/api/rebuild/url-file", {"filename": "../secrets.txt"}))
    assert resp.status_code == 400, resp.text


def test_rebuild_url_file_missing_returns_404(tmp_path):
    missing = f"missing-{uuid.uuid4().hex}.txt"
    resp = asyncio.run(_post(tmp_path, "/ui/api/rebuild/url-file", {"filename": missing}))
    assert resp.status_code == 404, resp.text


def test_rebuild_url_file_happy_path_can_start(tmp_path, monkeypatch):
    url_file = Path("txt") / f"test-urls-{uuid.uuid4().hex}.txt"
    url_file.write_text("https://example.com\n", encoding="utf-8")

    def _fake_run(_filename: str, _state: AppState) -> IngestionSummary:
        return IngestionSummary(documents=1, chunks=2)

    async def _fake_refresh(_state: AppState) -> None:
        return None

    monkeypatch.setattr(app_mod, "_run_rebuild_urls_file", _fake_run)
    monkeypatch.setattr(app_mod, "refresh_retriever", _fake_refresh)

    try:
        resp = asyncio.run(_post(tmp_path, "/ui/api/rebuild/url-file", {"filename": url_file.name}))
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"documents": 1, "chunks": 2}
    finally:
        try:
            url_file.unlink()
        except FileNotFoundError:
            pass
