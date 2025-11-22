from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import duckdb
import yaml
import re
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic.warnings import PydanticDeprecatedSince20

from mcp_server.server import DEFAULT_HTTP_PATH, build_app
from mcp_server.toolset import RAGToolset
from utils.config import AppConfig
from utils.database import read_metadata
from utils.memory_db import bootstrap_memory_db
from utils.embeddings import DEFAULT_CLOUD_EMBED_MODEL, EmbeddingProvider
from utils.env import load_env_file
from utils.items import ItemService
from utils.pipeline import rebuild_rag_from_sitemap, rebuild_rag_from_urls
from utils.retrieval import Retriever
from utils.reranker import CLOUD_RERANKER_MODEL, PassageReranker

# Filtra el warning de Pydantic generado por crawl4ai (Config en BaseModel).
warnings.filterwarnings(
    "ignore",
    category=PydanticDeprecatedSince20,
    module="pydantic._internal._config",
)

logger = logging.getLogger(__name__)


def ensure_extension_directory() -> Path:
    base = Path(".duckdb/extensions")
    base.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DUCKDB_EXTENSION_DIRECTORY", str(base.resolve()))
    return base


def resolve_model_names(config: AppConfig) -> dict[str, str]:
    mode = config.main.mode
    embedding_model = (
        config.embeddings.model_name
        if mode == "local"
        else config.embeddings.cloud_model_name or DEFAULT_CLOUD_EMBED_MODEL
    )
    reranker_model = (
        config.reranker.model_name
        if mode == "local"
        else config.reranker.cloud_model_name or CLOUD_RERANKER_MODEL
    )
    return {"embedding": embedding_model, "reranker": reranker_model}


def _install_extensions(db_path: Path) -> None:
    install_connection = duckdb.connect(db_path.as_posix())
    try:
        for extension in ("vss", "fts"):
            try:
                install_connection.execute(f"LOAD {extension};")
            except Exception:
                try:
                    install_connection.execute(f"INSTALL {extension};")
                    install_connection.execute(f"LOAD {extension};")
                except Exception as exc:
                    # Robustez: sin red/no instaladas, continuar sin romper el arranque
                    logger.warning(
                        "DuckDB: no fue posible INSTALL/LOAD de '%s'. Continuando sin la extensión: %s",
                        extension,
                        exc,
                    )
    finally:
        install_connection.close()


def _open_ro_connection(db_path: Path):
    # Use read_write everywhere to avoid DuckDB config mismatch across connections
    connection = duckdb.connect(db_path.as_posix(), read_only=False)
    for extension in ("vss", "fts"):
        try:
            connection.execute(f"LOAD {extension};")
        except Exception as exc:
            logger.warning(
                "DuckDB: no se pudo LOAD '%s' en la conexión principal; búsquedas pueden degradarse: %s",
                extension,
                exc,
            )
    return connection


def _rag_schema_available(db_path: Path) -> bool:
    connection = duckdb.connect(db_path.as_posix(), read_only=False)
    try:
        rows = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name IN ('docs', 'chunks');"
        ).fetchall()
        found = {row[0] for row in rows if row and row[0]}
        return "docs" in found and "chunks" in found
    except Exception:
        logger.info("No se pudo comprobar el esquema RAG; se asumirá no disponible.")
        return False
    finally:
        connection.close()


def load_retriever(config: AppConfig) -> Tuple[Optional[Retriever], Optional[Any]]:
    db_path = Path(config.database.path)
    if not db_path.exists():
        return None, None

    rag_ready = _rag_schema_available(db_path)
    if not rag_ready:
        connection = duckdb.connect(db_path.as_posix(), read_only=False)
        logger.info("BD presente pero sin esquema RAG; se cargarán solo tablas generales.")
        return None, connection

    ensure_extension_directory()
    _install_extensions(db_path)
    try:
        connection = _open_ro_connection(db_path)
    except Exception as exc:  # pragma: no cover - apertura de BD protegida
        logger.exception("No se pudo abrir la BD en modo lectura.")
        raise RuntimeError(f"No se pudo abrir la BD: {exc}") from exc
    embedder = EmbeddingProvider(config.embeddings, mode=config.main.mode)
    reranker = (
        PassageReranker(config.reranker, mode=config.main.mode)
        if config.retrieval.enable_rerank
        else None
    )
    retriever = Retriever(connection, config.retrieval, embedder, reranker=reranker)
    return retriever, connection


def _available_tools_from_config(config: AppConfig) -> Optional[list[str]]:
    tools_config = getattr(config, "mcp", None)
    if not tools_config:
        return None
    selected_tools = None
    if tools_config.tool_sets:
        if tools_config.active_set and tools_config.active_set in tools_config.tool_sets:
            selected_tools = tools_config.tool_sets.get(tools_config.active_set) or {}
        elif "rag" in tools_config.tool_sets:
            selected_tools = tools_config.tool_sets.get("rag") or {}
    if selected_tools:
        return [name for name, enabled in selected_tools.items() if enabled]
    if tools_config.tools:
        return [name for name, enabled in tools_config.tools.items() if enabled]
    return None


TOOL_GROUPS = {
    "rag": ["dense_search", "lexical_search", "hybrid_search", "chunks_by_url"],
    "cli": ["cli_start", "cli_send", "cli_stop", "cli_restart"],
    "items": [
        "store_item",
        "update_item",
        "get_item",
        "list_items",
        "search_items",
        "patch_doc",
        "delete_item",
    ],
}


@dataclass
class AppState:
    config: AppConfig
    toolset: RAGToolset
    retriever: Optional[Retriever]
    connection: Optional[Any]
    item_service: Optional[ItemService] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    rebuild_running: bool = False
    config_dirty: bool = False
    restart_required: bool = False

    def close_connection(self) -> None:
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
        self.connection = None
        self.retriever = None
        self.toolset.update_retriever(None)


def _get_db_overview(connection) -> Dict[str, Any]:
    overview = {
        "docs_count": 0,
        "sample_urls": [],
    }
    if not connection:
        return overview
    try:
        row = connection.execute("SELECT COUNT(*) FROM docs;").fetchone()
        overview["docs_count"] = int(row[0]) if row else 0
        rows = connection.execute(
            "SELECT url FROM docs ORDER BY created_at DESC LIMIT 5;"
        ).fetchall()
        overview["sample_urls"] = [r[0] for r in rows if r and r[0]]
    except Exception:
        logger.info("No se pudo obtener el resumen de la BD.")
    return overview


def _is_docker() -> bool:
    """Best-effort detection of Docker runtime.

    Returns True if a typical Docker marker is present or an explicit
    environment variable is provided. This avoids binding the server to
    all interfaces when running locally, while keeping Docker behavior.
    """
    try:
        if os.getenv("CONTAINER_NAME"):
            return True
        return Path("/.dockerenv").exists()
    except Exception:
        return False


def _resolve_host_binding() -> Tuple[str, str]:
    """Return the bind host and the host to display in logs."""
    host_env = (os.getenv("APP_HOST") or "").strip()
    host = host_env or "0.0.0.0"
    display_host = "localhost" if host == "0.0.0.0" else host
    return host, display_host


_RESERVED_PROJECT_SLUGS = {
    "api", "ui", "mcp", "docs", "items", "projects", "status", "settings", "rebuild", "log"
}


def _normalize_slug(value: str) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    s = re.sub(r"--+", "-", s)
    return s


async def refresh_retriever(state: AppState) -> None:
    retriever, connection = await asyncio.to_thread(load_retriever, state.config)
    state.connection = connection
    state.retriever = retriever
    state.toolset.update_retriever(retriever)


def _load_config_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=500, detail="config.yaml no encontrado.")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.error("No se pudo leer config.yaml: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo leer config.yaml.") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="config.yaml debe ser un mapa YAML.")
    return data


def _persist_enabled_tools(enabled: list[str], state: AppState, config_path: Path) -> dict[str, Any]:
    """
    Persiste la lista de tools activas en config.yaml respetando la estructura existente (tools o tool_sets).
    No aplica cambios en caliente; marca restart_required para que la UI avise.
    """
    data = _load_config_dict(config_path)
    mcp_section = data.get("mcp") or {}
    available = state.toolset.available_tools()

    if mcp_section.get("tool_sets"):
        active_set = mcp_section.get("active_set")
        selected_set = active_set if active_set and active_set in mcp_section["tool_sets"] else None
        if not selected_set and mcp_section["tool_sets"]:
            selected_set = next(iter(mcp_section["tool_sets"].keys()))
            mcp_section["active_set"] = selected_set
        selected_map = mcp_section["tool_sets"].get(selected_set) if selected_set else None
        if selected_set and isinstance(selected_map, dict):
            new_map = {name: name in enabled for name in set(selected_map.keys()) | set(enabled)}
            mcp_section["tool_sets"][selected_set] = dict(sorted(new_map.items()))
        else:
            # Crea un set "rag" si no existía
            mcp_section.setdefault("tool_sets", {})
            mcp_section["tool_sets"]["rag"] = {name: name in enabled for name in available}
            mcp_section["active_set"] = "rag"
    else:
        current_tools = mcp_section.get("tools") or {}
        base_keys = set(current_tools.keys()) | set(available) | set(enabled)
        mcp_section["tools"] = {name: name in enabled for name in base_keys}

    data["mcp"] = mcp_section
    try:
        config_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")
    except Exception as exc:
        logger.error("No se pudo escribir config.yaml: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo guardar config.yaml.") from exc

    # Refresca la config en memoria para consultas posteriores
    state.config = AppConfig.from_dict(data)
    state.restart_required = True
    return {"mcp": mcp_section}


def _persist_settings(payload: Dict[str, Any], state: AppState, config_path: Path) -> dict[str, Any]:
    """
    Persiste ajustes de modo/modelos/reranker y ajustes UI (selected_project) en config.yaml.
    Solo los cambios de modo/modelos/reranker requieren restart/rebuild.
    """
    data = _load_config_dict(config_path)
    updated_any = False
    updated_runtime = False

    mcp_data = data.get("mcp") or {}
    data["mcp"] = mcp_data

    main_data = data.get("main") or {}
    mode = (payload.get("mode") or main_data.get("mode") or "local").strip().lower()
    if mode != main_data.get("mode"):
        main_data["mode"] = mode
        updated_any = True
        updated_runtime = True
    data["main"] = main_data

    embed_data = data.get("embeddings") or {}
    if payload.get("embedding_local") is not None:
        new_val = payload.get("embedding_local").strip()
        if new_val and new_val != embed_data.get("model_name"):
            embed_data["model_name"] = new_val
            updated_any = True
            updated_runtime = True
    if payload.get("embedding_cloud") is not None:
        new_val = payload.get("embedding_cloud").strip()
        if new_val != embed_data.get("cloud_model_name"):
            embed_data["cloud_model_name"] = new_val or None
            updated_any = True
            updated_runtime = True
    data["embeddings"] = embed_data

    reranker_data = data.get("reranker") or {}
    if payload.get("reranker_local") is not None:
        new_val = payload.get("reranker_local").strip()
        if new_val and new_val != reranker_data.get("model_name"):
            reranker_data["model_name"] = new_val
            updated_any = True
            updated_runtime = True
    if payload.get("reranker_cloud") is not None:
        new_val = payload.get("reranker_cloud").strip()
        if new_val != reranker_data.get("cloud_model_name"):
            reranker_data["cloud_model_name"] = new_val or None
            updated_any = True
            updated_runtime = True
    data["reranker"] = reranker_data

    retrieval_data = data.get("retrieval") or {}
    if "enable_rerank" in payload:
        desired = bool(payload.get("enable_rerank"))
        if desired != retrieval_data.get("enable_rerank", False):
            retrieval_data["enable_rerank"] = desired
            updated_any = True
            updated_runtime = True
    data["retrieval"] = retrieval_data

    # UI-only settings (no restart/rebuild)
    ui_data = data.get("ui") or {}
    if payload.get("selected_project") is not None:
        new_slug = (payload.get("selected_project") or "").strip() or None
        if new_slug != ui_data.get("selected_project"):
            ui_data["selected_project"] = new_slug
            updated_any = True
    data["ui"] = ui_data

    try:
        config_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False), encoding="utf-8")
    except Exception as exc:
        logger.error("No se pudo escribir config.yaml: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo guardar config.yaml.") from exc

    state.config = AppConfig.from_dict(data)
    state.config_dirty = updated_runtime or state.config_dirty
    state.restart_required = state.restart_required or updated_runtime
    return {"updated": updated_any, "needs_rebuild": state.config_dirty, "needs_restart": state.restart_required}


def _run_rebuild_sitemap(url: str, config: AppConfig):
    ensure_extension_directory()
    embedder = EmbeddingProvider(config.embeddings, mode=config.main.mode)
    return rebuild_rag_from_sitemap(url, config, embedder)


def _run_rebuild_urls_file(filename: str, config: AppConfig):
    path = Path("txt") / filename
    if not path.is_file():
        raise FileNotFoundError(f"No se encontró el fichero {path}")
    content = path.read_text(encoding="utf-8")
    urls: list[str] = []
    for line in content.splitlines():
        candidate = line.strip()
        if candidate and not candidate.startswith("#"):
            urls.append(candidate)
    if not urls:
        raise ValueError("El fichero no contiene URLs válidas.")
    ensure_extension_directory()
    embedder = EmbeddingProvider(config.embeddings, mode=config.main.mode)
    return rebuild_rag_from_urls(urls, config, embedder)


def create_web_app(state: AppState, base_path: str) -> FastAPI:
    app = build_app(state.toolset, base_path=base_path)
    templates = Jinja2Templates(directory="templates")
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/")
    async def root(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/templates/AGENTS.txt")
    @app.get("/ui/api/guidelines")
    async def get_agents_guidelines():
        from fastapi.responses import PlainTextResponse

        candidates = [Path("templates/AGENTS.txt"), Path("AGENTS.md")]
        agents_path = next((path for path in candidates if path.exists()), None)
        if not agents_path:
            raise HTTPException(status_code=404, detail="Guidelines file not found")
        try:
            content = agents_path.read_text(encoding="utf-8")
            return PlainTextResponse(content=content)
        except Exception as exc:
            logger.error("Error reading guidelines file: %s", exc)
            raise HTTPException(
                status_code=500, detail="Error reading guidelines file"
            ) from exc

    @app.get("/ui/api/status")
    async def api_status(request: Request):
        overview = await asyncio.to_thread(_get_db_overview, state.connection)
        models = resolve_model_names(state.config)
        # Build full MCP URL (scheme + host:port + path)
        base_url = str(request.base_url).rstrip("/")
        mcp_url = f"{base_url}{base_path}"
        # Selected project and item counts
        selected_project = (state.config.ui.selected_project or "").strip() or None
        items_counts = None
        if selected_project and state.item_service:
            try:
                items_counts = state.item_service.count_items_by_type(project=selected_project, project_id=None)
            except Exception:
                items_counts = None
        runtime_tools = list(state.toolset.list_tools().keys())
        return {
            "mode": state.config.main.mode,
            "embedding": models["embedding"],
            "reranker": models["reranker"],
            "docs_count": overview["docs_count"],
            "sample_urls": overview["sample_urls"],
            "db_exists": bool(state.connection),
            "mcp_path": base_path,
            "mcp_url": mcp_url,
            "runtime_tools": runtime_tools,
            "tool_groups": TOOL_GROUPS,
            "selected_project": selected_project or "",
            "items_counts": items_counts or {"memory": 0, "doc": 0, "bug": 0, "todo": 0},
            "rebuild_running": state.rebuild_running,
            "needs_rebuild": state.config_dirty,
            "restart_required": state.restart_required,
        }

    @app.get("/ui/api/tools")
    async def api_tools():
        tool_names = state.toolset.available_tools()
        configured = _available_tools_from_config(state.config)
        enabled = configured if configured is not None else list(state.toolset.list_tools().keys())
        return {
            "available": tool_names,
            "enabled": enabled,
            "runtime_enabled": list(state.toolset.list_tools().keys()),
            "groups": TOOL_GROUPS,
            "needs_restart": state.restart_required,
        }

    @app.post("/ui/api/tools")
    async def api_tools_update(payload: Dict[str, Any]):
        enabled = payload.get("enabled") or []
        if not isinstance(enabled, list):
            raise HTTPException(status_code=400, detail="enabled debe ser una lista.")
        config_path = Path("config.yaml")
        _persist_enabled_tools(enabled, state, config_path)
        return {
            "enabled": enabled,
            "needs_restart": True,
            "message": "Tools saved to config.yaml. Restart MCP to apply.",
        }

    @app.get("/ui/api/settings")
    async def api_settings():
        cfg = state.config
        return {
            "mode": cfg.main.mode,
            "embedding_local": cfg.embeddings.model_name,
            "embedding_cloud": cfg.embeddings.cloud_model_name,
            "reranker_local": cfg.reranker.model_name,
            "reranker_cloud": cfg.reranker.cloud_model_name,
            "enable_rerank": cfg.retrieval.enable_rerank,
            "selected_project": (cfg.ui.selected_project or ""),
            "needs_rebuild": state.config_dirty,
            "needs_restart": state.restart_required,
        }

    @app.post("/ui/api/settings")
    async def api_settings_update(payload: Dict[str, Any]):
        config_path = Path("config.yaml")
        # Normalize and validate selected_project existence when provided
        normalized_payload = dict(payload)
        if payload.get("selected_project") is not None:
            sel_raw = (payload.get("selected_project") or "").strip()
            sel = _normalize_slug(sel_raw)
            if sel and state.item_service and not state.item_service.project_exists(sel):
                raise HTTPException(status_code=400, detail=f"Selected project does not exist: '{sel}'. Create it first.")
            normalized_payload["selected_project"] = sel or None
        result = _persist_settings(normalized_payload, state, config_path)
        return {
            "updated": result["updated"],
            "needs_rebuild": result["needs_rebuild"],
            "needs_restart": result["needs_restart"],
            "message": "Settings saved to config.yaml. Restart MCP and rebuild the index to apply.",
        }

    @app.get("/ui/api/url-files")
    async def api_url_files():
        txt_dir = Path("txt")
        txt_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(p.name for p in txt_dir.glob("*.txt") if p.is_file())
        return {"files": files}

    @app.post("/ui/api/rebuild/sitemap")
    async def api_rebuild_sitemap(payload: Dict[str, Any]):
        url = (payload.get("url") or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="Debes proporcionar una URL de sitemap.")
        async with state.lock:
            if state.rebuild_running:
                raise HTTPException(status_code=409, detail="Ya hay una reconstrucción en curso.")
            state.rebuild_running = True
            try:
                state.close_connection()
                summary = await asyncio.to_thread(_run_rebuild_sitemap, url, state.config)
                await refresh_retriever(state)
                state.config_dirty = False
                return {"documents": summary.documents, "chunks": summary.chunks}
            finally:
                state.rebuild_running = False

    @app.post("/ui/api/rebuild/url-file")
    async def api_rebuild_file(payload: Dict[str, Any]):
        filename = (payload.get("filename") or "").strip()
        if not filename:
            raise HTTPException(status_code=400, detail="Debes indicar un fichero de URLs.")
        async with state.lock:
            if state.rebuild_running:
                raise HTTPException(status_code=409, detail="Ya hay una reconstrucción en curso.")
            state.rebuild_running = True
            try:
                state.close_connection()
                summary = await asyncio.to_thread(_run_rebuild_urls_file, filename, state.config)
                await refresh_retriever(state)
                state.config_dirty = False
                return {"documents": summary.documents, "chunks": summary.chunks}
            finally:
                state.rebuild_running = False

    @app.get("/ui/api/docs")
    async def api_docs():
        if not state.connection:
            return {"docs": []}
        try:
            rows = state.connection.execute(
                "SELECT doc_id, url, title, created_at FROM docs ORDER BY created_at DESC LIMIT 50;"
            ).fetchall()
            docs = []
            for row in rows:
                doc_id, url, title, created_at = row
                docs.append({"doc_id": doc_id, "url": url, "title": title, "created_at": str(created_at)})
            return {"docs": docs}
        except Exception as exc:
            logger.warning("Failed to list documents: %s", exc)
            raise HTTPException(status_code=500, detail=f"Failed to list documents: {exc}") from exc

    @app.get("/ui/api/projects")
    async def api_projects():
        try:
            projects = state.item_service.list_projects() if state.item_service else []
            return {"projects": projects}
        except Exception as exc:
            logger.warning("Failed to list projects: %s", exc)
            raise HTTPException(status_code=500, detail=f"Failed to list projects: {exc}") from exc

    @app.post("/ui/api/projects")
    async def api_project_create(payload: Dict[str, Any]):
        if not state.item_service:
            raise HTTPException(status_code=500, detail="Items service unavailable.")
        raw_slug = (payload.get("slug") or "").strip()
        slug = _normalize_slug(raw_slug)
        name = (payload.get("name") or "").strip() or None
        if not slug:
            raise HTTPException(status_code=400, detail="You must provide a project slug.")
        if slug in _RESERVED_PROJECT_SLUGS:
            raise HTTPException(status_code=400, detail=f"Reserved project slug: '{slug}'. Choose a different one.")
        if len(slug) < 3 or len(slug) > 64:
            raise HTTPException(status_code=400, detail="Project slug must be between 3 and 64 characters.")
        try:
            # If exists, return 409 to signal duplicate
            if state.item_service.project_exists(slug):
                raise HTTPException(status_code=409, detail="Project already exists.")
            proj = state.item_service.create_project(slug, name=name)
            return {"project": proj}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid project data: {exc}") from exc
        except Exception as exc:
            logger.warning("Failed to create project '%s': %s", slug, exc)
            raise HTTPException(status_code=500, detail=f"Failed to create project '{slug}': {exc}") from exc

    @app.delete("/ui/api/projects/{slug}")
    async def api_project_delete(slug: str):
        if not state.item_service:
            raise HTTPException(status_code=500, detail="Items service unavailable.")
        active = (state.config.ui.selected_project or "").strip().lower()
        target = (slug or "").strip().lower()
        if not target:
            raise HTTPException(status_code=400, detail="You must provide a project slug to delete.")
        if active and target == active:
            raise HTTPException(status_code=400, detail="You cannot delete the active project. Change the selected project first.")
        try:
            summary = state.item_service.delete_project(project=target, project_id=None)
            return {
                "deleted": True,
                "project": slug,
                "deleted_items": summary.get("deleted_items", 0),
                "message": f"Project '{slug}' deleted with all associated items.",
            }
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=f"Project not found: {exc}") from exc
        except Exception as exc:
            logger.warning("Failed to delete project '%s': %s", slug, exc)
            raise HTTPException(status_code=500, detail=f"Failed to delete project '{slug}': {exc}") from exc

    @app.get("/ui/api/items")
    async def api_items(project: Optional[str] = None, project_id: Optional[str] = None, item_type: Optional[str] = None,
                        status: Optional[str] = None, tags: Optional[str] = None, limit: int = 50,
                        query: Optional[str] = None):
        if not state.item_service:
            raise HTTPException(status_code=500, detail="Items service unavailable.")
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        try:
            if query:
                items = state.item_service.search_items(
                    project=project, project_id=project_id, query=query, item_type=item_type, tags=tag_list, limit=limit
                )
            else:
                items = state.item_service.list_items(
                    project=project, project_id=project_id, item_type=item_type, status=status, tags=tag_list, limit=limit
                )
            return {"items": [asdict(item) for item in items]}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid request: {exc}") from exc
        except Exception as exc:
            logger.warning("Failed to list items (project=%s): %s", project or project_id, exc)
            raise HTTPException(status_code=500, detail=f"Failed to list items for project='{project or project_id}': {exc}") from exc

    @app.get("/ui/api/items/{item_id}")
    async def api_item_detail(item_id: str, project: Optional[str] = None, project_id: Optional[str] = None):
        if not state.item_service:
            raise HTTPException(status_code=500, detail="Items service unavailable.")
        try:
            item = state.item_service.get_item(project=project, project_id=project_id, item_id=item_id)
            return {"item": asdict(item)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=f"Not found: {exc}") from exc
        except Exception as exc:
            logger.warning("Failed to get item '%s': %s", item_id, exc)
            raise HTTPException(status_code=500, detail=f"Failed to get item '{item_id}': {exc}") from exc

    @app.post("/ui/api/items")
    async def api_items_create(payload: Dict[str, Any]):
        if not state.item_service:
            raise HTTPException(status_code=500, detail="Items service unavailable.")
        try:
            item = state.item_service.store_item(
                project=payload.get("project"),
                project_id=payload.get("project_id"),
                item_type=payload.get("type"),
                title=payload.get("title"),
                body_md=payload.get("body_md"),
                tags=payload.get("tags"),
                status=payload.get("status"),
                meta=payload.get("meta"),
            )
            return {"item": asdict(item)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid item data: {exc}") from exc
        except Exception as exc:
            logger.warning("Failed to create item: %s", exc)
            raise HTTPException(status_code=500, detail=f"Failed to create item: {exc}") from exc

    @app.patch("/ui/api/items/{item_id}")
    async def api_items_update(item_id: str, payload: Dict[str, Any]):
        if not state.item_service:
            raise HTTPException(status_code=500, detail="Items service unavailable.")
        project = payload.get("project")
        project_id = payload.get("project_id")
        try:
            if "unified_diff" in payload:
                item = state.item_service.patch_doc(
                    project=project,
                    project_id=project_id,
                    item_id=item_id,
                    unified_diff=payload.get("unified_diff", ""),
                    expected_version=payload.get("expected_version"),
                )
            else:
                item = state.item_service.update_item(
                    project=project,
                    project_id=project_id,
                    item_id=item_id,
                    fields=payload.get("fields", {}),
                )
            return {"item": asdict(item)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid update: {exc}") from exc
        except Exception as exc:
            logger.warning("Failed to update item '%s': %s", item_id, exc)
            raise HTTPException(status_code=500, detail=f"Failed to update item '{item_id}': {exc}") from exc

    @app.post("/ui/api/items/{item_id}/body")
    async def api_items_replace_body(item_id: str, payload: Dict[str, Any]):
        if not state.item_service:
            raise HTTPException(status_code=500, detail="Items service unavailable.")
        project = payload.get("project")
        project_id = payload.get("project_id")
        new_body = payload.get("body_md", "")
        expected_version = payload.get("expected_version")
        try:
            item = state.item_service.replace_body(
                project=project,
                project_id=project_id,
                item_id=item_id,
                new_body=new_body,
                expected_version=expected_version,
            )
            return {"item": asdict(item)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid body update: {exc}") from exc
        except Exception as exc:
            logger.warning("Failed to update body for item '%s': %s", item_id, exc)
            raise HTTPException(status_code=500, detail=f"Failed to update item body '{item_id}': {exc}") from exc

    @app.delete("/ui/api/items/{item_id}")
    async def api_items_delete(item_id: str, project: Optional[str] = None, project_id: Optional[str] = None):
        if not state.item_service:
            raise HTTPException(status_code=500, detail="Items service unavailable.")
        try:
            state.item_service.delete_item(project=project, project_id=project_id, item_id=item_id)
            return {"deleted": True}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=f"Not found: {exc}") from exc
        except Exception as exc:
            logger.warning("Failed to delete item '%s': %s", item_id, exc)
            raise HTTPException(status_code=500, detail=f"Failed to delete item '{item_id}': {exc}") from exc

    @app.post("/ui/api/restart")
    async def api_restart():
        """
        Reinicia el servicio. Requiere CONTAINER_NAME para reiniciar el contenedor Docker.
        No hay relanzado de subproceso fuera de Docker.
        """
        container_name = os.getenv("CONTAINER_NAME")
        if not container_name:
            raise HTTPException(
                status_code=400,
                detail="CONTAINER_NAME no está definido; reinicio disponible solo en entorno Docker.",
            )
        try:
            result = subprocess.run(
                ["docker", "restart", container_name],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("Docker restart output: %s", result.stdout.strip())
            return {"status": "restarting", "message": f"Docker container {container_name} restarting"}
        except subprocess.CalledProcessError as exc:
            logger.error("No se pudo reiniciar el contenedor %s: %s", container_name, exc.stderr)
            raise HTTPException(status_code=500, detail=f"No se pudo reiniciar el contenedor {container_name}.")

    return app


def main() -> None:
    load_env_file()
    try:
        config = AppConfig.load("config.yaml")
    except Exception as exc:
        raise SystemExit(f"No se pudo cargar config.yaml: {exc}") from exc

    # Inicializa la base de datos de memoria (SQLite) para projects/items
    try:
        bootstrap_memory_db(config.memory_database)
    except Exception as exc:
        raise SystemExit(f"No se pudo inicializar la base de datos de memoria: {exc}") from exc

    enabled_tools = _available_tools_from_config(config)
    retriever, connection = load_retriever(config)
    # ItemService ahora usa la BBDD SQLite dedicada a memoria
    item_service = ItemService(config.memory_database)
    toolset = RAGToolset(
        retriever=retriever,
        item_service=item_service,
        enabled_tools=enabled_tools,
        cli_logs_enabled=getattr(getattr(config, "mcp", None), "cli_logs_enabled", True),
    )
    state = AppState(
        config=config,
        toolset=toolset,
        retriever=retriever,
        connection=connection,
        item_service=item_service,
    )

    http_path = os.getenv("MCP_HTTP_PATH", DEFAULT_HTTP_PATH)
    http_path = f"/{http_path.lstrip('/')}"

    app = create_web_app(state, base_path=http_path)

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    host, display_host = _resolve_host_binding()
    port = int(os.getenv("APP_PORT", "8000"))
    logger.info(
        "Servidor web+MCP en http://%s:%s (MCP en %s). Abre http://%s:%s en tu navegador.",
        host,
        port,
        http_path,
        display_host,
        port,
    )
    uvicorn.run(app, host=host, port=port, log_level=level_name.lower())


if __name__ == "__main__":
    main()
