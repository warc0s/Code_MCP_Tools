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
- El board tipo kanban solo aparece en `Todo`.
- Para Memory/Docs/Bugs se muestra un listado de tarjetas simple (grid), con:
  - Título, tipo, versión, tags
  - Extracto del body (cuando aplica)
  - Acciones: ✎ Edit (inline), Delete

## Edición inline (✎)
- Al pulsar ✎ en una card se despliega un editor inline con:
  - Title, Status, Tags, Meta (JSON)
  - Body (markdown) para todos los tipos (`memory`, `doc`, `bug`, `todo`)
- Guardado:
  - Primero actualiza metadatos vía `PATCH /ui/api/items/{id}` con `fields`
  - Después, si hay body, lo guarda con `POST /ui/api/items/{id}/body` (aplica a cualquier tipo)
  - Se usa `expected_version` para el body, evitando pisar cambios concurrentes.

## Eliminaciones y estado
- Delete en cada card elimina el item del proyecto activo.
- En Todo, el drag-and-drop entre columnas cambia el `status`.

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
- El campo Meta (JSON) en el formulario “Create item” aplica automáticamente la plantilla del subtipo seleccionado al cambiar entre pestañas (Memory/Docs/Bugs/Todo), evitando que se arrastre contenido del subtipo anterior.

## Validación manual
- Settings: guardar proyecto y ver el pill del header actualizado.
- Memory:
  - Crear item en cada subtipo.
  - Listar y editar inline.
  - En Todo: mover tarjetas entre columnas y editar con ✎.

Si algo no responde como esperas, dime el caso concreto y lo ajusto.
