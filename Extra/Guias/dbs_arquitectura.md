# División de BBDD: RAG (DuckDB) / Memoria (SQLite)

Esta guía documenta la separación de la base de datos en dos motores, manteniendo compatibilidad con la UI/MCP y sin romper flujos existentes.

## Objetivo
- Aislar el almacén RAG (documentos/chunks/índices VSS/FTS) en DuckDB.
- Mover `projects/items` (memoria interna, docs, bugs, todo) a SQLite para operaciones CRUD ligeras y estabilidad.

## Configuración (`config.yaml`)
```yaml
main:
  mode: local

database:          # RAG (DuckDB)
  path: data/rag.duckdb

memory_database:   # Memoria (SQLite)
  path: data/memory.sqlite3
```

- Si `memory_database` no existe, se crea automáticamente al arrancar.
- `database.path` mantiene su semántica anterior: es el RAG (DuckDB).

## Esquemas
- DuckDB (RAG): `docs`, `chunks`, `metadata` (con VSS/FTS si están disponibles).
- SQLite (memoria): `projects`, `items`, `metadata`.
  - `items` incluye las columnas base (`tags`, `status`, `meta`) y columnas tipadas por tipo añadidas idempotentemente (p. ej., `bug_severity`, `todo_kind`, `memory_topic`, etc.). Las listas tipadas se almacenan como JSON en columnas `TEXT`.

## Ámbito
- RAG: global para toda la app; un rebuild sustituye el índice completo.
- Memoria: por proyecto; la UI y tools operan sobre el `ui.selected_project`.

## Arranque y wiring
- `app.py` inicializa SQLite con `bootstrap_memory_db` y crea `ItemService` con `memory_database`.
- El `Retriever` se abre contra DuckDB usando `database.path` como antes.
- Los endpoints UI/MCP siguen igual; sólo cambia dónde vive la persistencia.

## Notas técnicas
- En SQLite se aplica `PRAGMA foreign_keys=ON` y `PRAGMA busy_timeout=5000` por conexión. Las rutas internas que solicitan `read_only=True` abren la BBDD con URI `mode=ro`, por lo que cualquier escritura accidental falla en el motor.
- Columnas `tags`/`meta` se almacenan como `TEXT` (JSON serializado) y se normalizan via `json.dumps/loads` en `ItemService`. Los campos tipados se guardan en columnas específicas para queries simples y UX más clara.
- En búsquedas sobre items, `CAST(... AS VARCHAR)` se sustituyó por `lower(i.meta)` para compatibilidad SQLite.
- En el rebuild del RAG, DuckDB ya no intenta crear índices sobre `items`.

## Migraciones
- Fase de desarrollo: no se migra desde DuckDB a SQLite automáticamente (no mantenemos datos previos). Si hubiera items previos en DuckDB, recrea manualmente en el nuevo proyecto.
