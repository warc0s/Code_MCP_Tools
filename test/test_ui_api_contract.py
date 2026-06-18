from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import httpx

from app import AppState, create_web_app
from mcp_server.toolset import RAGToolset
from utils.config import AppConfig
from utils.items import ItemService
from utils.memory_db import bootstrap_memory_db


async def _with_client(tmp_path: Path, callback, selected_project: str | None = None):
    config_data = {
        "database": {"path": str(tmp_path / "missing.duckdb")},
        "memory_database": {"path": str(tmp_path / "memory.sqlite3")},
    }
    if selected_project is not None:
        config_data["ui"] = {"selected_project": selected_project}
    config = AppConfig.from_dict(config_data)
    bootstrap_memory_db(config.memory_database)
    item_service = ItemService(config.memory_database)
    toolset = RAGToolset(retriever=None, item_service=item_service, enabled_tools=None)
    state = AppState(
        config=config,
        toolset=toolset,
        retriever=None,
        connection=None,
        item_service=item_service,
        lock=asyncio.Lock(),
    )
    web_app = create_web_app(state, base_path="/mcp")
    try:
        transport = httpx.ASGITransport(app=web_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await callback(client)
    finally:
        state.executor.shutdown(wait=True, cancel_futures=True)


def test_project_create_endpoint_is_idempotent(tmp_path):
    async def run(client):
        first = await client.post("/ui/api/projects", json={"slug": "contract-project"})
        second = await client.post("/ui/api/projects", json={"slug": "contract-project"})
        return first, second

    first, second = asyncio.run(_with_client(tmp_path, run))

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["project"]["id"] == second.json()["project"]["id"]
    assert first.json()["project"]["created"] is True
    assert second.json()["project"]["created"] is False


def test_item_detail_without_project_is_bad_request(tmp_path):
    async def run(client):
        return await client.get("/ui/api/items/missing-item")

    response = asyncio.run(_with_client(tmp_path, run))

    assert response.status_code == 400
    assert "Invalid request" in response.text


def test_status_reports_rag_ready_flag(tmp_path):
    async def run(client):
        return await client.get("/ui/api/status")

    response = asyncio.run(_with_client(tmp_path, run))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["db_exists"] is False
    assert payload["rag_ready"] is False


def test_item_create_rejects_non_object_meta_as_400(tmp_path):
    async def run(client):
        await client.post("/ui/api/projects", json={"slug": "meta-api"})
        return await client.post(
            "/ui/api/items",
            json={
                "project": "meta-api",
                "type": "todo",
                "title": "Bad meta",
                "status": "pending",
                "meta": "bad",
                "typed": {
                    "kind": "feature",
                    "acceptance_criteria": ["works"],
                    "priority": "p1",
                },
            },
        )

    response = asyncio.run(_with_client(tmp_path, run))

    assert response.status_code == 400
    assert "meta must be an object" in response.text


def test_active_project_delete_guard_uses_canonical_slug(tmp_path):
    async def run(client):
        created = await client.post("/ui/api/projects", json={"slug": "my-project"})
        deleted = await client.delete("/ui/api/projects/my_project")
        projects = await client.get("/ui/api/projects")
        return created, deleted, projects

    created, deleted, projects = asyncio.run(
        _with_client(tmp_path, run, selected_project="my-project")
    )

    assert created.status_code == 200, created.text
    assert deleted.status_code == 400, deleted.text
    assert "active project" in deleted.text
    slugs = {project["slug"] for project in projects.json()["projects"]}
    assert "my-project" in slugs


def test_rebuild_progress_update_initializes_without_deadlock(tmp_path):
    config = AppConfig.from_dict(
        {
            "database": {"path": str(tmp_path / "missing.duckdb")},
            "memory_database": {"path": str(tmp_path / "memory.sqlite3")},
        }
    )
    toolset = RAGToolset(retriever=None, item_service=None, enabled_tools=None)
    state = AppState(
        config=config,
        toolset=toolset,
        retriever=None,
        connection=None,
        item_service=None,
        lock=asyncio.Lock(),
    )
    errors: list[BaseException] = []
    finished = threading.Event()

    def update() -> None:
        try:
            state.update_rebuild_progress({"stage": "first", "message": "First progress"})
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=update, daemon=True)
    thread.start()

    assert finished.wait(1.0), "update_rebuild_progress deadlocked on empty progress"
    assert errors == []
    snapshot = state.snapshot_rebuild_progress()
    assert snapshot["stage"] == "first"
    assert snapshot["message"] == "First progress"
    assert snapshot["seq"] >= 2
