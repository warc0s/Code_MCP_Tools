# DB Split: RAG (DuckDB) / Memory (SQLite)

This guide documents the database split across two engines while keeping UI/MCP compatibility and preserving existing flows.

## Goal

- Isolate the RAG store (documents/chunks/VSS/FTS indexes) in DuckDB.
- Move `projects/items` (internal memory, docs, bugs, todos) to SQLite for lightweight CRUD operations and stability.

## Configuration (`config.yaml`)

```yaml
main:
  mode: local

database:          # RAG (DuckDB)
  path: data/rag.duckdb

memory_database:   # Memory (SQLite)
  path: data/memory.sqlite3
```

- If `memory_database` does not exist, it is created automatically at startup.
- `database.path` keeps its previous meaning: it is the RAG DuckDB path.

## Schemas

- DuckDB (RAG): `docs`, `chunks`, `metadata` (with VSS/FTS when available).
- SQLite (memory): `projects`, `items`, `metadata`.
  - `items` includes base columns (`tags`, `status`, `meta`) and per-type typed columns added idempotently (for example `bug_severity`, `todo_kind`, `memory_topic`, etc.). Typed lists are stored as JSON in `TEXT` columns.

## Scope

- RAG: global for the whole app; a rebuild replaces the full index.
- Memory: project-scoped; the UI and tools operate on `ui.selected_project`.

## Startup And Wiring

- `app.py` initializes SQLite with `bootstrap_memory_db` and creates `ItemService` with `memory_database`.
- `Retriever` opens DuckDB through `database.path` as before.
- UI/MCP endpoints remain the same; only the persistence location changes.

## Technical Notes

- SQLite applies `PRAGMA foreign_keys=ON` and `PRAGMA busy_timeout=5000` per connection. Internal paths that request `read_only=True` open the DB with URI `mode=ro`, so accidental writes fail in the engine.
- `tags`/`meta` columns are stored as `TEXT` (serialized JSON) and normalized through `json.dumps/loads` in `ItemService`. Typed fields are stored in specific columns for simpler queries and clearer UX.
- Item searches replaced `CAST(... AS VARCHAR)` with `lower(i.meta)` for SQLite compatibility.
- RAG rebuild no longer tries to create indexes over `items`.

## Migrations

- Development phase: there is no automatic migration from DuckDB to SQLite because old data is not preserved. If previous items existed in DuckDB, recreate them manually in the new project.
