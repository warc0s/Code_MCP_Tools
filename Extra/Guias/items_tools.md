# MCP Tools For Projects/Items

Scope note: Items tools operate per project. The RAG index is global and does not depend on the selected project.

## Base Schema

- Tables `projects` (id/slug/name+timestamps) and `items` with `type` (`memory`, `doc`, `bug`, `todo`), `title`, `body_md`, `tags` (JSON), `status`, `meta` (JSON), `version`, `created_at`, and `updated_at`.
- Since the DB split, this schema lives in SQLite (`memory_database.path`). It is created automatically at startup. RAG rebuilds only affect DuckDB (`docs/chunks/metadata`).

## Types And Conventions

- `memory`: decisions, invariants, mental maps, and internal agent guidelines. Required fields go in `typed` (topic, decision, context, rationale); `meta` is reserved for optional extras.
- `doc`: markdown documentation that would previously live in `docs/`. It is versioned and edited through `patch_doc`. `typed` exposes optional `authors` and `related_docs`; the rest goes in optional `meta`.
- `bug`: bug graveyard; required fields go in `typed` (`severity`, `reproduction`, `expected`, `root_cause`). `meta` is used for extras (logs_excerpt, resolution_criteria, related_files, done_summary, etc.).
- `todo`: tasks; required fields go in `typed` (`kind`, `acceptance_criteria`, `priority`). Optional `meta` can hold `dependencies`, `related_files`, `done_summary`, etc.
- `tags` and `status` are normalized to lowercase; `status` only accepts `pending`, `in_progress`, `to_verify`, and `resolved`. `project` can be a slug or `project_id`. Note: projects are no longer created automatically.

## New MCP Tools

- `store_item(project?, project_id?, type, title, body_md?, tags?, status?, meta?, typed?)` -> creates an item. `typed` carries required per-type fields; `meta` is optional for extras.
- `update_item(project?, project_id?, id, fields)` -> updates `title`, `tags`, `status`, optional `meta`, partial `typed`, and bumps `version`.
- `get_item(project?, project_id?, id)` -> retrieves one item.
- `list_items(project?, project_id?, type?, status?, tags?, limit=50)` -> filtered list ordered by `updated_at`.
- `search_items(project?, project_id?, query, type?, tags?, limit=50)` -> basic search over `title`, `body_md`, and `meta`. The query is treated as literal text.
- `update_item` also validates `typed` for `doc`; `authors` and `related_docs` are stored as JSON lists (always arrays after validation).
- `patch_doc(project?, project_id?, id, unified_diff, expected_version?)` -> applies a unified diff to a `doc` item `body_md`, bumps version, and updates `updated_at`.
- `delete_item(project?, project_id?, id)` -> deletes the requested item.

### Project Operations (UI API)

- `GET /ui/api/projects` -> lists projects with item counts.
- `POST /ui/api/projects { slug, name? }` -> creates a project idempotently.
- `DELETE /ui/api/projects/{slug}` -> deletes the project and all its items. Deleting the active project (`ui.selected_project`) is not allowed. The UI shows English confirmations explaining the impact before proceeding.

Advanced note: the backend keeps FKs enabled and deletes projects in a single SQLite transaction (`items` for the project, then `project`). Concurrent deletion of the same project does not report double success: one call deletes and the other receives `Project not found`.

Notes:
- Always pass `project` or `project_id` (at least one) to every tool. If the project does not exist, tools return `Project not found`; create it first from the UI (Projects) or through `/ui/api/projects`.
- `typed` is required in `store_item` for `memory`, `bug`, and `todo` (fallback from `meta` is accepted for compatibility). For `doc`, it is optional.
- `patch_doc` validates `expected_version` when provided; it fails if the version does not match or the diff does not apply to the current body.
- Output includes `project_slug`, `project_name`, `version`, and timestamps; `item.typed` includes persisted typed fields.

### `unified_diff` Example For `patch_doc`

Replace one line in a `doc`:

```
@@ -5,1 +5,1 @@
-- Use for Dashboard Status cards
+- Used by Dashboard Status cards
```

- Context lines start with a space.
- In bullets that already start with `- `, you will see `--` in the diff (the diff marker plus the real bullet).
- You can include several hunks when editing non-contiguous sections.
