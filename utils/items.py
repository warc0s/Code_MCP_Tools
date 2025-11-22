"""
Gestión de proyectos e items (memory/doc/bug/todo) sobre SQLite (memoria).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import sqlite3

from utils.config import MemoryDatabaseConfig

ALLOWED_ITEM_TYPES = {"memory", "doc", "bug", "todo"}
ALLOWED_STATUSES = {"pending", "in_progress", "to_verify", "resolved"}


@dataclass
class ItemRecord:
    id: str
    project_id: str
    project_slug: str
    project_name: str
    type: str
    title: str
    body_md: str
    tags: List[str]
    status: Optional[str]
    meta: Dict[str, Any]
    version: int
    created_at: str
    updated_at: str


def _normalize_tags(tags: Optional[Iterable[str]]) -> list[str]:
    normalized: list[str] = []
    for tag in tags or []:
        if tag is None:
            continue
        candidate = str(tag).strip().lower()
        if candidate:
            normalized.append(candidate)
    return normalized


def _normalize_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    candidate = status.strip().lower()
    return candidate or None


def _validate_status(status: Optional[str]) -> Optional[str]:
    normalized = _normalize_status(status)
    if normalized is None:
        return None
    if normalized not in ALLOWED_STATUSES:
        raise ValueError(
            f"status debe ser uno de {', '.join(sorted(ALLOWED_STATUSES))}."
        )
    return normalized


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip().lower()).strip("-")
    return cleaned or uuid.uuid4().hex


def _parse_json(value: Any, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def apply_unified_diff(original: str, diff_text: str) -> str:
    """
    Aplica un diff unificado (como los usados en git) al texto original.
    Levanta ValueError si el diff no aplica limpiamente.
    """
    if not diff_text.strip():
        raise ValueError("El diff proporcionado está vacío.")
    orig_lines = original.splitlines(keepends=True)
    diff_lines = diff_text.splitlines(keepends=True)
    output: list[str] = []
    orig_idx = 0
    i = 0

    def parse_range(chunk: str) -> tuple[int, int]:
        if "," in chunk:
            start, count = chunk.split(",", 1)
            return int(start), int(count)
        return int(chunk), 1

    while i < len(diff_lines):
        line = diff_lines[i]
        if not line.startswith("@@"):
            i += 1
            continue
        header = line.strip().split()
        if len(header) < 3:
            raise ValueError("Hunk de diff inválido.")
        old_range = header[1][1:]
        start_old, _ = parse_range(old_range)
        # Copia el bloque previo sin cambios
        target_idx = max(0, start_old - 1)
        if target_idx > len(orig_lines):
            raise ValueError("El diff apunta fuera del texto original.")
        output.extend(orig_lines[orig_idx:target_idx])
        orig_idx = target_idx
        i += 1
        while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
            current = diff_lines[i]
            if current.startswith(" "):
                if orig_idx >= len(orig_lines):
                    raise ValueError("El diff no coincide con el texto base (contexto insuficiente).")
                expected = orig_lines[orig_idx]
                candidate = current[1:]
                if expected != candidate:
                    raise ValueError("El diff no coincide con el texto base (contexto distinto).")
                output.append(expected)
                orig_idx += 1
            elif current.startswith("-"):
                if orig_idx >= len(orig_lines):
                    raise ValueError("El diff elimina líneas que no existen en el original.")
                expected = orig_lines[orig_idx]
                candidate = current[1:]
                if expected != candidate:
                    raise ValueError("El diff no coincide con el texto base (línea a eliminar).")
                orig_idx += 1
            elif current.startswith("+"):
                output.append(current[1:])
            elif current.startswith("\\"):
                # Línea '\ No newline at end of file' u otras anotaciones: se ignoran
                pass
            else:
                raise ValueError("Diff con prefijo de línea desconocido.")
            i += 1
    output.extend(orig_lines[orig_idx:])
    return "".join(output)


class ItemService:
    def __init__(self, db_config: MemoryDatabaseConfig):
        self.db_path = db_config.path

    def _connect(self, read_only: bool = False):
        # Always open read_write for simplicity; enforce foreign keys.
        conn = sqlite3.connect(self.db_path.as_posix())
        try:
            conn.execute("PRAGMA foreign_keys=ON;")
        except Exception:
            pass
        return conn

    def _ensure_project(
        self, project: Optional[str], project_id: Optional[str], create_missing: bool = False
    ) -> tuple[str, str, str]:
        if not project and not project_id:
            raise ValueError("You must provide either 'project' or 'project_id'.")
        with self._connect(read_only=False) as conn:
            if project_id:
                row = conn.execute(
                    "SELECT id, slug, name FROM projects WHERE id = ? LIMIT 1;", [project_id]
                ).fetchone()
                if not row:
                    raise ValueError("project_id not found.")
                return row[0], row[1], row[2]
            slug = _slugify(project or "")
            row = conn.execute(
                "SELECT id, slug, name FROM projects WHERE slug = ? LIMIT 1;", [slug]
            ).fetchone()
            if row:
                return row[0], row[1], row[2]
            if not create_missing:
                # Do not create projects implicitly from tool calls
                raise ValueError(
                    f"Project not found: slug='{slug}'. Verify the name or create the project first."
                )
            new_id = uuid.uuid4().hex
            name = (project or slug).strip() or slug
            conn.execute(
                "INSERT INTO projects (id, slug, name) VALUES (?, ?, ?);",
                [new_id, slug, name],
            )
            return new_id, slug, name

    def create_project(self, slug_or_name: str, name: Optional[str] = None) -> dict[str, Any]:
        """Crea un proyecto vacío si no existe y devuelve sus datos.

        Si ya existe, devuelve la info existente (id/slug/name/created_at, items_count).
        """
        slug = _slugify(slug_or_name or "")
        if not slug:
            raise ValueError("Debes indicar un slug válido.")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, slug, name, created_at FROM projects WHERE slug = ? LIMIT 1;",
                [slug],
            ).fetchone()
            created = False
            if row:
                project_id, pslug, pname, created_at = row
            else:
                project_id = uuid.uuid4().hex
                pname = (name or slug).strip() or slug
                conn.execute(
                    "INSERT INTO projects (id, slug, name) VALUES (?, ?, ?);",
                    [project_id, slug, pname],
                )
                created = True
                created_at = conn.execute(
                    "SELECT created_at FROM projects WHERE id = ?;",
                    [project_id],
                ).fetchone()[0]
        # Count items
        with self._connect(read_only=False) as conn:
            items_count = conn.execute(
                "SELECT COUNT(1) FROM items WHERE project_id = ?;",
                [project_id],
            ).fetchone()[0]
        return {
            "id": project_id,
            "slug": slug,
            "name": pname,
            "created_at": str(created_at),
            "items_count": int(items_count or 0),
            "created": bool(created),
        }

    def project_exists(self, slug: str) -> bool:
        """Check if a project with the given slug exists."""
        s = _slugify(slug or "")
        if not s:
            return False
        with self._connect(read_only=False) as conn:
            row = conn.execute(
                "SELECT 1 FROM projects WHERE slug = ? LIMIT 1;",
                [s],
            ).fetchone()
            return bool(row)

    def list_projects(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect(read_only=False) as conn:
            rows = conn.execute(
                """
                SELECT
                    p.id,
                    p.slug,
                    p.name,
                    p.created_at,
                    COUNT(i.id) AS items_count
                FROM projects AS p
                LEFT JOIN items AS i ON i.project_id = p.id
                GROUP BY p.id, p.slug, p.name, p.created_at
                ORDER BY p.created_at DESC
                LIMIT ?;
                """,
                [max(1, min(limit, 200))],
            ).fetchall()
        result = []
        for row in rows:
            project_id, slug, name, created_at, items_count = row
            result.append(
                {
                    "id": project_id,
                    "slug": slug,
                    "name": name,
                    "created_at": str(created_at),
                    "items_count": int(items_count or 0),
                }
            )
        return result

    def _row_to_item(self, row) -> ItemRecord:
        (
            item_id,
            project_id,
            project_slug,
            project_name,
            item_type,
            title,
            body_md,
            tags,
            status,
            meta,
            version,
            created_at,
            updated_at,
        ) = row
        tags_data = _parse_json(tags, [])
        if not isinstance(tags_data, list):
            tags_data = []
        meta_data = _parse_json(meta, {})
        if not isinstance(meta_data, dict):
            meta_data = {}

        return ItemRecord(
            id=item_id,
            project_id=project_id,
            project_slug=project_slug,
            project_name=project_name,
            type=item_type,
            title=title or "",
            body_md=body_md or "",
            tags=tags_data,
            status=status,
            meta=meta_data,
            version=int(version),
            created_at=str(created_at),
            updated_at=str(updated_at),
        )

    def store_item(
        self,
        project: Optional[str],
        project_id: Optional[str],
        item_type: str,
        title: str,
        body_md: Optional[str],
        tags: Optional[Iterable[str]] = None,
        status: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> ItemRecord:
        if item_type not in ALLOWED_ITEM_TYPES:
            raise ValueError("Unsupported item type.")
        if not (title or "").strip():
            raise ValueError("Title must not be empty.")
        normalized_tags = _normalize_tags(tags)
        normalized_status = _validate_status(status)
        # Require an existing project; do not auto-create on store
        project_db_id, project_slug, project_name = self._ensure_project(project, project_id, create_missing=False)
        item_id = uuid.uuid4().hex
        payload_meta = meta or {}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO items (id, project_id, type, title, body_md, tags, status, meta, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1);
                """,
                [
                    item_id,
                    project_db_id,
                    item_type,
                    title.strip(),
                    body_md or "",
                    json.dumps(normalized_tags),
                    normalized_status,
                    json.dumps(payload_meta),
                ],
            )
        return self.get_item(project=project_slug, project_id=project_db_id, item_id=item_id)

    def get_item(
        self, project: Optional[str], project_id: Optional[str], item_id: str
    ) -> ItemRecord:
        project_db_id, project_slug, project_name = self._ensure_project(project, project_id)
        with self._connect(read_only=False) as conn:
            row = conn.execute(
                """
                SELECT
                    i.id,
                    i.project_id,
                    p.slug,
                    p.name,
                    i.type,
                    i.title,
                    i.body_md,
                    i.tags,
                    i.status,
                    i.meta,
                    i.version,
                    i.created_at,
                    i.updated_at
                FROM items AS i
                JOIN projects AS p ON p.id = i.project_id
                WHERE i.id = ? AND i.project_id = ?
                LIMIT 1;
                """,
                [item_id, project_db_id],
            ).fetchone()
        if not row:
            raise ValueError("Item not found for the specified project.")
        record = self._row_to_item(row)
        # Garantiza que devolvemos el slug actualizado
        record.project_slug = project_slug
        record.project_name = project_name
        return record

    def update_item(
        self,
        project: Optional[str],
        project_id: Optional[str],
        item_id: str,
        fields: Dict[str, Any],
    ) -> ItemRecord:
        if not fields or not isinstance(fields, dict):
            raise ValueError("'fields' must be an object with at least one property.")
        if "body_md" in fields:
            raise ValueError("To update the body use 'patch_doc' or the '/body' endpoint.")
        project_db_id, project_slug, project_name = self._ensure_project(project, project_id)
        updates: list[str] = []
        params: list[Any] = []
        if "title" in fields:
            new_title = (fields.get("title") or "").strip()
            if not new_title:
                raise ValueError("'title' must not be empty.")
            updates.append("title = ?")
            params.append(new_title)
        if "tags" in fields:
            updates.append("tags = ?")
            params.append(json.dumps(_normalize_tags(fields.get("tags"))))
        if "status" in fields:
            updates.append("status = ?")
            params.append(_validate_status(fields.get("status")))
        if "meta" in fields:
            updates.append("meta = ?")
            params.append(json.dumps(fields.get("meta") or {}))
        if not updates:
            raise ValueError("'fields' contains no updatable properties.")
        updates.append("version = version + 1")
        updates.append("updated_at = CURRENT_TIMESTAMP")
        sql = f"""
            UPDATE items
            SET {", ".join(updates)}
            WHERE id = ? AND project_id = ?;
        """
        params.extend([item_id, project_db_id])
        with self._connect() as conn:
            result = conn.execute(sql, params)
            if result.rowcount == 0:
                raise ValueError("Item not found to update.")
        return self.get_item(project=project_slug, project_id=project_db_id, item_id=item_id)

    def list_items(
        self,
        project: Optional[str],
        project_id: Optional[str],
        item_type: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        limit: int = 50,
    ) -> list[ItemRecord]:
        project_db_id, _, _ = self._ensure_project(project, project_id)
        tag_filter = _normalize_tags(tags)
        sql = """
            SELECT
                i.id,
                i.project_id,
                p.slug,
                p.name,
                i.type,
                i.title,
                i.body_md,
                i.tags,
                i.status,
                i.meta,
                i.version,
                i.created_at,
                i.updated_at
            FROM items AS i
            JOIN projects AS p ON p.id = i.project_id
            WHERE i.project_id = ?
        """
        params: list[Any] = [project_db_id]
        if item_type:
            if item_type not in ALLOWED_ITEM_TYPES:
                raise ValueError("Unsupported type for filtering.")
            sql += " AND i.type = ?"
            params.append(item_type)
        if status:
            sql += " AND i.status = ?"
            params.append(_normalize_status(status))
        sql += " ORDER BY i.updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self._connect(read_only=False) as conn:
            rows = conn.execute(sql, params).fetchall()
        records = [self._row_to_item(row) for row in rows]
        if tag_filter:
            records = [
                rec for rec in records if all(tag in rec.tags for tag in tag_filter)
            ]
        return records

    def search_items(
        self,
        project: Optional[str],
        project_id: Optional[str],
        query: str,
        item_type: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        limit: int = 50,
    ) -> list[ItemRecord]:
        cleaned = (query or "").strip()
        if not cleaned:
            raise ValueError("'query' must not be empty.")
        project_db_id, _, _ = self._ensure_project(project, project_id)
        tag_filter = _normalize_tags(tags)
        sql = """
            SELECT
                i.id,
                i.project_id,
                p.slug,
                p.name,
                i.type,
                i.title,
                i.body_md,
                i.tags,
                i.status,
                i.meta,
                i.version,
                i.created_at,
                i.updated_at
            FROM items AS i
            JOIN projects AS p ON p.id = i.project_id
            WHERE i.project_id = ?
        """
        params: list[Any] = [project_db_id]
        if item_type:
            if item_type not in ALLOWED_ITEM_TYPES:
                raise ValueError("Unsupported type for filtering.")
            sql += " AND i.type = ?"
            params.append(item_type)
        pattern = f"%{cleaned.lower()}%"
        sql += " AND (lower(i.title) LIKE ? OR lower(i.body_md) LIKE ? OR lower(i.meta) LIKE ?)"
        params.extend([pattern, pattern, pattern])
        sql += " ORDER BY i.updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        records = [self._row_to_item(row) for row in rows]
        if tag_filter:
            records = [
                rec for rec in records if all(tag in rec.tags for tag in tag_filter)
            ]
        return records

    def patch_doc(
        self,
        project: Optional[str],
        project_id: Optional[str],
        item_id: str,
        unified_diff: str,
        expected_version: Optional[int] = None,
    ) -> ItemRecord:
        item = self.get_item(project=project, project_id=project_id, item_id=item_id)
        if item.type != "doc":
            raise ValueError("'patch_doc' only applies to items of type 'doc'.")
        if expected_version is not None and item.version != expected_version:
            raise ValueError("Current version does not match 'expected_version'.")
        new_body = apply_unified_diff(item.body_md, unified_diff)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE items
                SET body_md = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND project_id = ?;
                """,
                [new_body, item.id, item.project_id],
            )
        return self.get_item(project=project, project_id=project_id, item_id=item.id)

    def replace_body(
        self,
        project: Optional[str],
        project_id: Optional[str],
        item_id: str,
        new_body: str,
        expected_version: Optional[int] = None,
    ) -> ItemRecord:
        """Replace item body_md directly and bump version.

        Applies to any item type. If expected_version is provided, enforce match.
        """
        item = self.get_item(project=project, project_id=project_id, item_id=item_id)
        if expected_version is not None and item.version != expected_version:
            raise ValueError("La versión actual no coincide con expected_version.")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE items
                SET body_md = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND project_id = ?;
                """,
                [new_body or "", item.id, item.project_id],
            )
        return self.get_item(project=project, project_id=project_id, item_id=item.id)

    def delete_item(self, project: Optional[str], project_id: Optional[str], item_id: str) -> None:
        project_db_id, _, _ = self._ensure_project(project, project_id)
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM items WHERE id = ? AND project_id = ?;",
                [item_id, project_db_id],
            )
            if result.rowcount == 0:
                raise ValueError("Item no encontrado para eliminar.")

    def count_items_by_type(self, project: Optional[str], project_id: Optional[str]) -> dict[str, int]:
        """Return item counts grouped by type for the given project.

        Fills missing types with 0 to ease UI rendering.
        """
        project_db_id, _, _ = self._ensure_project(project, project_id)
        with self._connect(read_only=False) as conn:
            rows = conn.execute(
                "SELECT type, COUNT(1) FROM items WHERE project_id = ? GROUP BY type;",
                [project_db_id],
            ).fetchall()
        counts = {"memory": 0, "doc": 0, "bug": 0, "todo": 0}
        for t, c in rows:
            if t in counts:
                counts[t] = int(c or 0)
        return counts

    def delete_project(self, project: Optional[str], project_id: Optional[str]) -> dict[str, int]:
        """Delete a project and all its items explicitly respecting FKs.

        En SQLite garantizamos FK activas y borramos primero hijos y luego el
        proyecto en dos fases para mantener mensajes claros.
        """
        proj_id, _slug, _name = self._ensure_project(project, project_id, create_missing=False)
        # Phase 1: delete children
        with self._connect(read_only=False) as conn:
            conn.execute("BEGIN TRANSACTION;")
            try:
                items_count = int(
                    conn.execute("SELECT COUNT(1) FROM items WHERE project_id = ?;", [proj_id]).fetchone()[0]
                    or 0
                )
                conn.execute("DELETE FROM items WHERE project_id = ?;", [proj_id])
                remaining = conn.execute("SELECT COUNT(1) FROM items WHERE project_id = ?;", [proj_id]).fetchone()[0]
                if int(remaining or 0) != 0:
                    raise RuntimeError("Could not delete all items for the project before removing it.")
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise

        # Phase 2: delete parent
        with self._connect(read_only=False) as conn:
            conn.execute("BEGIN TRANSACTION;")
            try:
                conn.execute("DELETE FROM projects WHERE id = ?;", [proj_id])
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
        return {"deleted_items": items_count, "deleted_projects": 1}


__all__ = ["ItemRecord", "ItemService", "apply_unified_diff"]
