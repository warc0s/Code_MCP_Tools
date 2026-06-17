# Refreshed Memory UI

This guide summarizes usability changes in the Memory section of the web panel.

## Important Scope Note

- RAG is global (not per project), and rebuild replaces the global index.
- Memory (`projects/items`) is project-scoped; project selection only affects Memory.

## Project Selection

- Project selection lives in Configuration > Settings > Project selection.
- Field: `Project slug` and a list of existing projects with a Use button.
- Main button: `Save and set project` creates the project if it does not exist, makes it active, and persists the selection in `config.yaml` (`ui.selected_project`). No restart is required.
- The active project appears in the header as a pill: Project: <slug>. The `Change` button jumps to Settings.

## Memory Tab

- Subtabs: Memory, Docs, Bugs, Todo.
- The Kanban board appears in `Todo` and now also in `Bugs`.
  - In `Bugs`, only two columns are shown: `Pending` and `Resolved`; every unresolved state (`pending`, `in_progress`, `to_verify`, or empty) is visually grouped under `Pending` so bugs created through API/MCP are not hidden.
- For Memory/Docs/Bugs, a simple card grid is shown with:
  - Title, type, version, tags
  - Body excerpt when available
  - Actions: Edit (inline), Delete

## Inline Editing

- Clicking Edit on a card opens an inline editor with:
  - Title, Status, Tags
  - Typed fields per type (required where applicable):
    - bug: severity, reproduction, expected, root_cause
    - todo: kind, acceptance_criteria, priority
    - memory: topic, decision, context, rationale
    - doc: authors, related_docs (optional)
  - Meta (JSON, optional; extras such as done_summary, related_files, logs...)
  - Body (markdown) for every type (`memory`, `doc`, `bug`, `todo`)
  - In `todo`, the priority hint is shown: `p0` (highest/urgent), `p1` (high), `p2` (normal)
- Save flow:
  - First updates metadata through `PATCH /ui/api/items/{id}` with `fields`
  - Then, if body is present, saves it with `POST /ui/api/items/{id}/body` (applies to any type)
  - Uses `expected_version` for body updates to avoid overwriting concurrent changes.

## Deletion And Status

- Delete on each card removes the item from the active project.
- In Todo and Bugs, drag-and-drop between columns changes `status`.
  - When moving to `Resolved`, if `meta.done_summary` (>=120 chars) or `meta.related_files` (at least one) are missing, the UI asks for them in a modal and saves them together with the status change.
  - The same applies from the inline editor: if you change `Status` to `Resolved` and those fields are missing, the same modal opens before saving.
  - Existing values preloaded into that modal are escaped before being inserted into HTML, including quotes and ampersands, to avoid attribute breakage or accidental injection.

## Removed Pieces

- “Project selection” block inside Memory (now in Settings).
- “Create empty project” button (the action is integrated into “Save and set project”).
- Global “Update metadata / Patch doc” editor.
- “Paste a diff” UI for `doc`: direct text editing and body replacement are now used.

## Technical Notes

- Project selection is persisted in the `ui` section of `config.yaml`:

```yaml
ui:
  selected_project: my-project
```

- New endpoint for body updates: `POST /ui/api/items/{id}/body` with JSON:

```json
{
  "project": "my-project",
  "body_md": "new markdown",
  "expected_version": 3
}
```

- Metadata editing still uses `PATCH /ui/api/items/{id}` with `fields`.

## Templates And UX

- The “Create item” form includes typed fields by type (required when applicable). The “Meta (JSON)” block is kept advanced/optional for extras; its template is auto-applied when changing type.

## “Show” Modal

- Each card includes a `Show` button that opens a read-only modal with the full item detail:
  - Basic data (type, version, status, tags)
  - `typed` fields by type (for example bug: severity, expected, reproduction, root_cause)
  - Extras in `meta` when present (done_summary, related_files, logs_excerpt, criteria)
  - Full body when present

### Suggested Fields By Type (Meta JSON)

- bug:
  - severity (high|medium|low)
  - reproduction (exact steps)
  - logs_excerpt (optional)
  - expected (expected behavior)
  - root_cause (root cause)
  - done_summary (implementation summary when resolving, >=120 chars)
  - resolution_criteria (list of checks to consider it resolved)
  - related_files (list of paths/URLs, optional)
- todo:
  - kind (bug_fix|refactor|feature|chore)
  - reproduction (optional)
  - acceptance_criteria (list)
  - dependencies (list)
  - priority (p0|p1|p2)
  - related_files (list of paths/URLs, optional)
  - done_summary (implementation summary when resolving, >=120 chars)

## Pydantic Validation And MCP Schema

- The backend validates `meta` with type-specific Pydantic models. If required fields are missing or values are invalid, it returns a detailed error (missing fields, invalid values) to make correction fast.
- MCP tools `store_item` and `update_item` expose a `oneOf` JSON Schema for `meta` per type (memory/doc/bug/todo).

## Auxiliary Meta Fields

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

If something behaves unexpectedly, report the concrete case and adjust the implementation.
