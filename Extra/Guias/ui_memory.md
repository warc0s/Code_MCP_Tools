# UI de Memory renovada

Esta guía resume los cambios de usabilidad en la sección Memory del panel web.

## Nota importante sobre ámbito
- El RAG es global (no por proyecto) y su rebuild reemplaza el índice global.
- La memoria (proyectos/items) es por proyecto; la selección de proyecto solo afecta Memory.

## Selección de proyecto
- La selección de proyecto se hace en Configuration > Settings > Project selection.
- Campo: `Project slug` y listado de proyectos existentes con botón Use.
- Botón principal: `Save and set project` crea el proyecto si no existe y lo deja como activo, además de persistir la selección en `config.yaml` (`ui.selected_project`). No requiere restart.
- El proyecto activo aparece en el header como un pill: Project: <slug>. Botón `Change` salta a Settings.

## Pestaña Memory
- Subpestañas: Memory, Docs, Bugs, Todo.
- El board tipo kanban aparece en `Todo` y ahora también en `Bugs`.
  - En `Bugs` se muestran solo dos columnas: `Pending` y `Resolved`; cualquier estado no resuelto (`pending`, `in_progress`, `to_verify` o vacío) se agrupa visualmente en `Pending` para no ocultar bugs creados desde API/MCP.
- Para Memory/Docs/Bugs se muestra un listado de tarjetas simple (grid), con:
  - Título, tipo, versión, tags
  - Extracto del body (cuando aplica)
  - Acciones: ✎ Edit (inline), Delete

## Edición inline (✎)
- Al pulsar ✎ en una card se despliega un editor inline con:
  - Title, Status, Tags
  - Typed fields por tipo (obligatorios):
    - bug: severity, reproduction, expected, root_cause
    - todo: kind, acceptance_criteria, priority
    - memory: topic, decision, context, rationale
    - doc: authors, related_docs (opcionales)
  - Meta (JSON, opcional; extras como done_summary, related_files, logs...)
  - Body (markdown) para todos los tipos (`memory`, `doc`, `bug`, `todo`)
  - En `todo` se muestra la ayuda de prioridad: `p0` (máxima/urgente), `p1` (alta), `p2` (normal)
- Guardado:
  - Primero actualiza metadatos vía `PATCH /ui/api/items/{id}` con `fields`
  - Después, si hay body, lo guarda con `POST /ui/api/items/{id}/body` (aplica a cualquier tipo)
  - Se usa `expected_version` para el body, evitando pisar cambios concurrentes.

## Eliminaciones y estado
- Delete en cada card elimina el item del proyecto activo.
- En Todo y Bugs, el drag-and-drop entre columnas cambia el `status`.
  - Al mover a `Resolved`, si faltan `meta.done_summary` (≥120 chars) o `meta.related_files` (al menos uno), la UI solicita esos datos en un modal y los guarda junto al cambio de estado.
  - También desde el editor inline: si cambias `Status` a `Resolved` y faltan esos campos, se abre el mismo modal antes de guardar.
  - Los valores preexistentes que se precargan en ese modal se escapan antes de insertarlos en HTML, incluyendo comillas y ampersands, para evitar roturas de atributos o inyección accidental.

## Qué desaparece
- Bloque de “Project selection” dentro de Memory (ahora en Settings).
- Botón “Create empty project” (la acción queda integrada en “Save and set project”).
- Editor global “Update metadata / Patch doc”.
- UI de “pegar un diff” para `doc`: ahora es edición textual directa y reemplazo de body.

## Notas técnicas
- La selección de proyecto se persiste en `config.yaml` sección `ui`:

```yaml
ui:
  selected_project: my-project
```

- Nuevo endpoint para actualizar body: `POST /ui/api/items/{id}/body` con JSON:

```json
{
  "project": "my-project",
  "body_md": "nuevo markdown",
  "expected_version": 3
}
```

- La edición de metadatos sigue usando `PATCH /ui/api/items/{id}` con `fields`.

## Plantillas y UX
- El formulario “Create item” incluye campos tipados por tipo (obligatorios cuando aplica). El bloque “Meta (JSON)” queda como avanzado/opcional para extras; su plantilla se auto-aplica al cambiar de tipo.

## Modal “Show”
- Cada tarjeta incluye un botón `Show` que abre un modal de solo lectura con el detalle completo del item:
  - Datos básicos (tipo, versión, estado, tags)
  - Campos `typed` por tipo (p. ej., bug: severity, expected, reproduction, root_cause)
  - Extras en `meta` cuando existan (done_summary, related_files, logs_excerpt, criteria)
  - Body completo si existe

### Campos sugeridos por tipo (Meta JSON)
- bug:
  - severity (high|medium|low)
  - reproduction (pasos exactos)
  - logs_excerpt (opcional)
  - expected (comportamiento esperado)
  - root_cause (causa raíz)
  - done_summary (resumen de implementación al resolver, ≥120 chars)
  - resolution_criteria (lista de checks para darlo por resuelto)
  - related_files (lista de rutas/URLs, opcional)
- todo:
  - kind (bug_fix|refactor|feature|chore)
  - reproduction (opcional)
  - acceptance_criteria (lista)
  - dependencies (lista)
  - priority (p0|p1|p2)
  - related_files (lista de rutas/URLs, opcional)
  - done_summary (resumen de implementación al resolver, ≥120 chars)

## Validación Pydantic y schema MCP
- El backend valida `meta` con modelos Pydantic específicos por tipo. Si faltan campos obligatorios o hay valores inválidos, devuelve un error detallado (campos faltantes, valores inválidos) para corregir rápidamente.
- Las tools MCP `store_item` y `update_item` exponen en su JSON Schema un `oneOf` con el esquema de `meta` para cada tipo (memory/doc/bug/todo).

## Campos meta auxiliares
- doc:
  - authors ([])
  - source_url
  - related_docs ([])
  - version_notes
- memory:
  - topic
  - decision
  - context
  - rationale
  - related_links ([])

Si algo no responde como esperas, dime el caso concreto y lo ajusto.
