# Tools MCP para proyectos/items

Nota de ámbito: las tools de Items operan por proyecto. El índice RAG es global y no depende del proyecto seleccionado.

## Esquema base
- Tablas `projects` (id/slug/name+timestamps) e `items` con `type` (`memory`, `doc`, `bug`, `todo`), `title`, `body_md`, `tags` (JSON), `status`, `meta` (JSON), `version`, `created_at`, `updated_at`.
- Desde la separación de BBDD, este esquema vive en SQLite (`memory_database.path`). Se crea automáticamente al arrancar. Los rebuild del RAG solo afectan a DuckDB (`docs/chunks/metadata`).

## Tipos y convenciones
- `memory`: decisiones, invariantes, mapas mentales, guías internas para el agente. Campos obligatorios pasan a `typed` (topic, decision, context, rationale); `meta` queda para extras opcionales.
- `doc`: documentación markdown que antes viviría en `docs/`. Se versiona y se edita vía `patch_doc`. `typed` expone `authors` y `related_docs` (opcionales); el resto va en `meta` opcional.
- `bug`: bug graveyard; campos obligatorios pasan a `typed` (`severity`, `reproduction`, `expected`, `root_cause`). `meta` se usa para extras (logs_excerpt, resolution_criteria, related_files, done_summary, etc.).
- `todo`: tareas; campos obligatorios pasan a `typed` (`kind`, `acceptance_criteria`, `priority`). `meta` opcional para `dependencies`, `related_files`, `done_summary`, etc.
- `tags` y `status` se normalizan en minúsculas; `status` solo admite `pending`, `in_progress`, `to_verify`, `resolved`. `project` puede ser slug o `project_id`. Nota: ya no se crean proyectos automáticamente.

## Tools MCP nuevas
- `store_item(project?, project_id?, type, title, body_md?, tags?, status?, meta?, typed?)` → crea item. `typed` recoge los campos obligatorios por tipo; `meta` es opcional para extras.
- `update_item(project?, project_id?, id, fields)` → actualiza `title`, `tags`, `status`, `meta` (opc) y `typed` (parcial) y sube `version`.
- `get_item(project?, project_id?, id)` → item único.
- `list_items(project?, project_id?, type?, status?, tags?, limit=50)` → listado filtrado, ordenado por `updated_at`.
- `search_items(project?, project_id?, query, type?, tags?, limit=50)` → búsqueda básica sobre `title`, `body_md` y `meta`.
- `patch_doc(project?, project_id?, id, unified_diff, expected_version?)` → aplica diff unificado al `body_md` de un `doc`, bump de versión y `updated_at`.
- `delete_item(project?, project_id?, id)` → elimina el item indicado.
  
### Operaciones de proyectos (API UI)
- `GET /ui/api/projects` → lista proyectos con recuento de items.
- `POST /ui/api/projects { slug, name? }` → crea proyecto idempotente.
- `DELETE /ui/api/projects/{slug}` → borra el proyecto y todos sus items. No se permite borrar el proyecto activo (`ui.selected_project`). La UI muestra confirmaciones en inglés explicando el impacto antes de proceder.

Nota avanzada: el backend mantiene las FKs activas y borra proyectos en una única transacción SQLite (`items` del proyecto y después `project`). El borrado concurrente de un mismo proyecto no reporta doble éxito: una llamada elimina y la otra recibe “Project not found”.

Notas:
- Usa siempre `project` o `project_id` (al menos uno) en cada tool. Si el proyecto no existe, las tools devolverán error de "Project not found"; créalo primero desde la UI (Projects) o mediante el endpoint `/ui/api/projects`.
- `typed` es obligatorio en `store_item` para `memory`, `bug` y `todo` (se acepta fallback desde `meta` por compatibilidad). Para `doc` es opcional.
- `patch_doc` valida `expected_version` si se pasa; falla si no coincide o si el diff no aplica al cuerpo actual.
- La salida devuelve `project_slug`, `project_name`, `version` y las marcas temporales; `item.typed` incluye los campos tipados persistidos.

### Ejemplo de `unified_diff` para `patch_doc`

Reemplazar una línea en un `doc`:

```
@@ -5,1 +5,1 @@
-- Use for Dashboard Status cards
+- Used by Dashboard Status cards
```

- Las líneas de contexto comienzan con espacio.
- En bullets que ya empiezan por `- `, verás `--` en el diff (primer `-` del diff + el bullet real).
- Puedes incluir varios hunks si editas en zonas no contiguas.
