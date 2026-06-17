"""
Project and item (memory/doc/bug/todo) management over SQLite memory storage.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import sqlite3

from utils.config import MemoryDatabaseConfig
from utils.item_meta import validate_meta, validate_typed_required

ALLOWED_ITEM_TYPES = {"memory", "doc", "bug", "todo"}
ALLOWED_STATUSES = {"pending", "in_progress", "to_verify", "resolved"}
RESERVED_PROJECT_SLUGS = {
    "api", "ui", "mcp", "docs", "items", "projects", "status", "settings", "rebuild", "log"
}


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
    typed: Dict[str, Any]
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


def _escape_like_token(value: str) -> str:
    """Escape SQL LIKE wildcards so query terms are matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _validate_status(status: Optional[str]) -> Optional[str]:
    normalized = _normalize_status(status)
    if normalized is None:
        return None
    if normalized not in ALLOWED_STATUSES:
        raise ValueError(
            f"status must be one of {', '.join(sorted(ALLOWED_STATUSES))}."
        )
    return normalized


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip().lower()).strip("-")
    cleaned = re.sub(r"--+", "-", cleaned)
    return cleaned


def normalize_project_slug(value: str) -> str:
    slug = _slugify(value or "")
    if not slug:
        raise ValueError("You must provide a valid project slug.")
    if slug in RESERVED_PROJECT_SLUGS:
        raise ValueError(f"Reserved project slug: '{slug}'. Choose a different one.")
    if len(slug) < 3 or len(slug) > 64:
        raise ValueError("Project slug must be between 3 and 64 characters.")
    return slug


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
        raise ValueError("Provided diff is empty.")
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
            raise ValueError("Invalid diff hunk header.")
        old_range = header[1][1:]
        start_old, _ = parse_range(old_range)
        # Copia el bloque previo sin cambios
        target_idx = max(0, start_old - 1)
        if target_idx > len(orig_lines):
            raise ValueError("Diff points outside the original text.")
        output.extend(orig_lines[orig_idx:target_idx])
        orig_idx = target_idx
        i += 1
        while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
            current = diff_lines[i]
            if current.startswith(" "):
                if orig_idx >= len(orig_lines):
                    raise ValueError("Diff does not match base text (insufficient context).")
                expected = orig_lines[orig_idx]
                candidate = current[1:]
                if expected != candidate:
                    raise ValueError("Diff does not match base text (different context).")
                output.append(expected)
                orig_idx += 1
            elif current.startswith("-"):
                if orig_idx >= len(orig_lines):
                    raise ValueError("Diff deletes lines that do not exist in original.")
                expected = orig_lines[orig_idx]
                candidate = current[1:]
                if expected != candidate:
                    raise ValueError("Diff does not match base text (line to remove).")
                orig_idx += 1
            elif current.startswith("+"):
                output.append(current[1:])
            elif current.startswith("\\"):
                # Line '\ No newline at end of file' or other annotations: ignore
                pass
            else:
                raise ValueError("Diff with unknown line prefix.")
            i += 1
    output.extend(orig_lines[orig_idx:])
    return "".join(output)


class ItemService:
    def __init__(self, db_config: MemoryDatabaseConfig):
        self.db_path = db_config.path

    def _connect(self, read_only: bool = False):
        db_path = self.db_path
        if read_only:
            conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
        else:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path.as_posix())
        try:
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA busy_timeout=5000;")
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
            slug = normalize_project_slug(project or "")
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
        """Create an empty project if missing and return its data.

        If it already exists, return existing info (id/slug/name/created_at, items_count).
        """
        slug = normalize_project_slug(slug_or_name or "")
        with self._connect() as conn:
            created = False
            project_id = uuid.uuid4().hex
            pname = (name or slug).strip() or slug
            try:
                conn.execute(
                    "INSERT INTO projects (id, slug, name) VALUES (?, ?, ?);",
                    [project_id, slug, pname],
                )
                created = True
            except sqlite3.IntegrityError:
                created = False
            row = conn.execute(
                "SELECT id, slug, name, created_at FROM projects WHERE slug = ? LIMIT 1;",
                [slug],
            ).fetchone()
            if not row:
                raise RuntimeError(f"Project '{slug}' could not be created.")
            project_id, _pslug, pname, created_at = row
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
        try:
            s = normalize_project_slug(slug or "")
        except ValueError:
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
            memory_topic,
            memory_decision,
            memory_context,
            memory_rationale,
            memory_related_links,
            doc_authors,
            doc_related_docs,
            bug_severity,
            bug_reproduction,
            bug_expected,
            bug_root_cause,
            todo_kind,
            todo_acceptance_criteria,
            todo_priority,
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

        # Build typed dict per type
        typed: Dict[str, Any] = {}
        if item_type == "memory":
            typed = {
                "topic": memory_topic or "",
                "decision": memory_decision or "",
                "context": memory_context or "",
                "rationale": memory_rationale or "",
                "related_links": _parse_json(memory_related_links, []),
            }
        elif item_type == "doc":
            typed = {
                "authors": _parse_json(doc_authors, []),
                "related_docs": _parse_json(doc_related_docs, []),
            }
        elif item_type == "bug":
            typed = {
                "severity": bug_severity or "",
                "reproduction": bug_reproduction or "",
                "expected": bug_expected or "",
                "root_cause": bug_root_cause or "",
            }
        elif item_type == "todo":
            typed = {
                "kind": todo_kind or "",
                "acceptance_criteria": _parse_json(todo_acceptance_criteria, []),
                "priority": todo_priority or "",
            }

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
            typed=typed,
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
        typed: Optional[Dict[str, Any]] = None,
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
        # Prepare typed payload (fallback from meta for backward compatibility)
        meta_obj = meta or {}
        typed_payload = dict(typed or {})
        if not typed_payload and isinstance(meta_obj, dict):
            if item_type == "memory":
                for k in ("topic", "decision", "context", "rationale", "related_links"):
                    if k in meta_obj:
                        typed_payload[k] = meta_obj.get(k)
            elif item_type == "bug":
                for k in ("severity", "reproduction", "expected", "root_cause"):
                    if k in meta_obj:
                        typed_payload[k] = meta_obj.get(k)
            elif item_type == "todo":
                for k in ("kind", "acceptance_criteria", "priority"):
                    if k in meta_obj:
                        typed_payload[k] = meta_obj.get(k)
            elif item_type == "doc":
                for k in ("authors", "related_docs"):
                    if k in meta_obj:
                        typed_payload[k] = meta_obj.get(k)
        # Validate typed required fields
        normalized_typed = validate_typed_required(item_type, typed_payload)
        # Validate and normalize meta (optional extras)
        payload_meta = validate_meta(item_type, meta_obj)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO items (
                    id, project_id, type, title, body_md, tags, status, meta,
                    memory_topic, memory_decision, memory_context, memory_rationale, memory_related_links,
                    doc_authors, doc_related_docs,
                    bug_severity, bug_reproduction, bug_expected, bug_root_cause,
                    todo_kind, todo_acceptance_criteria, todo_priority,
                    version
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    1
                );
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
                    # memory typed
                    normalized_typed.get("topic") if item_type == "memory" else None,
                    normalized_typed.get("decision") if item_type == "memory" else None,
                    normalized_typed.get("context") if item_type == "memory" else None,
                    normalized_typed.get("rationale") if item_type == "memory" else None,
                    json.dumps(normalized_typed.get("related_links", [])) if item_type == "memory" else None,
                    # doc typed
                    json.dumps(normalized_typed.get("authors", [])) if item_type == "doc" else None,
                    json.dumps(normalized_typed.get("related_docs", [])) if item_type == "doc" else None,
                    # bug typed
                    normalized_typed.get("severity") if item_type == "bug" else None,
                    normalized_typed.get("reproduction") if item_type == "bug" else None,
                    normalized_typed.get("expected") if item_type == "bug" else None,
                    normalized_typed.get("root_cause") if item_type == "bug" else None,
                    # todo typed
                    normalized_typed.get("kind") if item_type == "todo" else None,
                    json.dumps(normalized_typed.get("acceptance_criteria", [])) if item_type == "todo" else None,
                    normalized_typed.get("priority") if item_type == "todo" else None,
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
                    i.memory_topic,
                    i.memory_decision,
                    i.memory_context,
                    i.memory_rationale,
                    i.memory_related_links,
                    i.doc_authors,
                    i.doc_related_docs,
                    i.bug_severity,
                    i.bug_reproduction,
                    i.bug_expected,
                    i.bug_root_cause,
                    i.todo_kind,
                    i.todo_acceptance_criteria,
                    i.todo_priority,
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
        # Ensure the updated slug is returned.
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
        # Fetch current item to evaluate conditional constraints
        current_item = self.get_item(project=project, project_id=project_id, item_id=item_id)
        # Optional type hint: reject mismatches to help MCP/UI clients validate payloads
        hinted_type = fields.get("type") if isinstance(fields, dict) else None
        if hinted_type is not None:
            normalized = str(hinted_type).strip().lower()
            if normalized not in ALLOWED_ITEM_TYPES:
                raise ValueError("Unsupported type hint.")
            if normalized != current_item.type:
                raise ValueError(
                    f"Item type mismatch: requested '{normalized}' but item is '{current_item.type}'."
                )
        # Determine final status (after update) to enforce resolution requirements
        requested_status = fields.get("status") if isinstance(fields, dict) else None
        final_status = _validate_status(requested_status) if requested_status is not None else current_item.status

        # Determine candidate meta (merge strategy: if provided, use it; else current)
        candidate_meta_raw = fields.get("meta") if isinstance(fields, dict) else None
        candidate_meta = candidate_meta_raw if candidate_meta_raw is not None else (current_item.meta or {})
        # Normalize candidate meta shape according to item type for validations below
        normalized_candidate_meta = validate_meta(item_type=current_item.type, meta=candidate_meta)

        # Enforce meta requirements when resolving bug/todo items
        if final_status == "resolved" and current_item.type in {"bug", "todo"}:
            done_summary = (normalized_candidate_meta.get("done_summary") or "").strip()
            related_files = normalized_candidate_meta.get("related_files") or []
            # related_files must be a non-empty list of non-empty strings
            related_files_ok = isinstance(related_files, list) and any(
                (str(x).strip() for x in related_files if x is not None)
            )
            if len(done_summary) < 120 or not related_files_ok:
                raise ValueError(
                    "When resolving a bug/todo you must provide meta.done_summary (>= 120 chars) and meta.related_files (at least one)."
                )
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
            normalized_meta = validate_meta(item_type=current_item.type, meta=fields.get("meta"))
            updates.append("meta = ?")
            params.append(json.dumps(normalized_meta))
        # typed updates (optional and partial)
        typed_fields = fields.get("typed") if isinstance(fields, dict) else None
        if "typed" in fields and typed_fields is not None and not isinstance(typed_fields, dict):
            raise ValueError("'typed' must be an object.")
        if isinstance(typed_fields, dict) and typed_fields:
            # Merge with current to validate required for types that have them
            merged = {**(current_item.typed or {}), **typed_fields}
            normalized_typed = validate_typed_required(current_item.type, merged)
            if current_item.type == "memory":
                if "topic" in typed_fields:
                    updates.append("memory_topic = ?"); params.append(normalized_typed.get("topic"))
                if "decision" in typed_fields:
                    updates.append("memory_decision = ?"); params.append(normalized_typed.get("decision"))
                if "context" in typed_fields:
                    updates.append("memory_context = ?"); params.append(normalized_typed.get("context"))
                if "rationale" in typed_fields:
                    updates.append("memory_rationale = ?"); params.append(normalized_typed.get("rationale"))
                if "related_links" in typed_fields:
                    updates.append("memory_related_links = ?"); params.append(json.dumps(normalized_typed.get("related_links", [])))
            elif current_item.type == "doc":
                if "authors" in typed_fields:
                    updates.append("doc_authors = ?"); params.append(json.dumps(normalized_typed.get("authors", [])))
                if "related_docs" in typed_fields:
                    updates.append("doc_related_docs = ?"); params.append(json.dumps(normalized_typed.get("related_docs", [])))
            elif current_item.type == "bug":
                if "severity" in typed_fields:
                    updates.append("bug_severity = ?"); params.append(normalized_typed.get("severity"))
                if "reproduction" in typed_fields:
                    updates.append("bug_reproduction = ?"); params.append(normalized_typed.get("reproduction"))
                if "expected" in typed_fields:
                    updates.append("bug_expected = ?"); params.append(normalized_typed.get("expected"))
                if "root_cause" in typed_fields:
                    updates.append("bug_root_cause = ?"); params.append(normalized_typed.get("root_cause"))
            elif current_item.type == "todo":
                if "kind" in typed_fields:
                    updates.append("todo_kind = ?"); params.append(normalized_typed.get("kind"))
                if "acceptance_criteria" in typed_fields:
                    updates.append("todo_acceptance_criteria = ?"); params.append(json.dumps(normalized_typed.get("acceptance_criteria", [])))
                if "priority" in typed_fields:
                    updates.append("todo_priority = ?"); params.append(normalized_typed.get("priority"))
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
                i.memory_topic,
                i.memory_decision,
                i.memory_context,
                i.memory_rationale,
                i.memory_related_links,
                i.doc_authors,
                i.doc_related_docs,
                i.bug_severity,
                i.bug_reproduction,
                i.bug_expected,
                i.bug_root_cause,
                i.todo_kind,
                i.todo_acceptance_criteria,
                i.todo_priority,
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
            params.append(_validate_status(status))
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
                i.memory_topic,
                i.memory_decision,
                i.memory_context,
                i.memory_rationale,
                i.memory_related_links,
                i.doc_authors,
                i.doc_related_docs,
                i.bug_severity,
                i.bug_reproduction,
                i.bug_expected,
                i.bug_root_cause,
                i.todo_kind,
                i.todo_acceptance_criteria,
                i.todo_priority,
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
        pattern = f"%{_escape_like_token(cleaned.lower())}%"
        sql += (
            " AND ("
            "lower(i.title) LIKE ? ESCAPE '\\' "
            "OR lower(i.body_md) LIKE ? ESCAPE '\\' "
            "OR lower(i.meta) LIKE ? ESCAPE '\\'"
            ")"
        )
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
                raise ValueError("Current version does not match expected_version.")
        normalized_body = new_body or ""
        if normalized_body == item.body_md:
            return item
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE items
                SET body_md = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND project_id = ?;
                """,
                [normalized_body, item.id, item.project_id],
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
                raise ValueError("Item not found to delete.")

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

        The operation runs in a single SQLite transaction so concurrent delete
        attempts cannot report success for a project that another transaction
        already removed.
        """
        with self._connect(read_only=False) as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                if project_id:
                    row = conn.execute(
                        "SELECT id FROM projects WHERE id = ? LIMIT 1;",
                        [project_id],
                    ).fetchone()
                else:
                    slug = normalize_project_slug(project or "")
                    row = conn.execute(
                        "SELECT id FROM projects WHERE slug = ? LIMIT 1;",
                        [slug],
                    ).fetchone()
                if not row:
                    raise ValueError("Project not found.")
                proj_id = row[0]
                items_count = int(
                    conn.execute("SELECT COUNT(1) FROM items WHERE project_id = ?;", [proj_id]).fetchone()[0]
                    or 0
                )
                conn.execute("DELETE FROM items WHERE project_id = ?;", [proj_id])
                remaining = conn.execute("SELECT COUNT(1) FROM items WHERE project_id = ?;", [proj_id]).fetchone()[0]
                if int(remaining or 0) != 0:
                    raise RuntimeError("Could not delete all items for the project before removing it.")
                result = conn.execute("DELETE FROM projects WHERE id = ?;", [proj_id])
                if result.rowcount != 1:
                    raise ValueError("Project not found to delete.")
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
        return {"deleted_items": items_count, "deleted_projects": 1}


__all__ = ["ItemRecord", "ItemService", "apply_unified_diff", "normalize_project_slug"]
