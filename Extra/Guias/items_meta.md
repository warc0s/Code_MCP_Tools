# Meta por tipo (Memory/Docs/Bugs/Todos)

Esta guía detalla la estructura del campo `meta` para cada tipo de item, la validación y ejemplos prácticos.

## Resumen
- Validación: `meta` se valida con Pydantic por tipo, pero todos sus campos son opcionales (extras). Los campos obligatorios pasan a `typed` (por tipo), y se validan al crear y cuando aplica.
- Tools MCP (`store_item`, `update_item`): exponen `meta` (opc) y `typed` (obligatorio por tipo) en su JSON Schema.
- UI: la plantilla de `meta` se auto-aplica al cambiar subtabs; los campos `typed` se muestran como inputs dedicados por tipo.

## Campos por tipo
- memory (typed obligatorios)
  - topic (str)
  - decision (str)
  - context (str)
  - rationale (str)
  - related_links (list[str], opcional)
- doc (typed opcionales)
  - authors (list[str])
  - related_docs (list[str])
  - source_url, version_notes → `meta` (opcional)
- bug (typed obligatorios)
  - severity: "high" | "medium" | "low"
  - reproduction (str; pasos exactos)
  - expected (str)
  - root_cause (str)
  - extras (meta, opcional): logs_excerpt, resolution_criteria (list), screenshots (URLs), related_files (list), done_summary (resumen al resolver)
- todo (typed obligatorios)
  - kind: "bug_fix" | "refactor" | "feature" | "chore"
  - acceptance_criteria (list[str])
  - priority: "p0" | "p1" | "p2"
  - extras (meta, opcional): reproduction, dependencies, related_files, done_summary
  - done_summary (str, opcional; requerido al resolver, ≥120 chars)

## Ejemplos

### BUG con logs
```json
{
  "severity": "medium",
  "reproduction": "Open Memory → Todo, drag card quickly",
  "expected": "Single update to target status without flicker",
  "root_cause": "DOM reflow under heavy drag events",
  "logs_excerpt": "Console shows duplicate drop event; network quiet; no 500s",
  "done_summary": "explain the implemented change, rationale and how it fixes the issue. Include relevant context and trade-offs so that future readers understand the approach.",
  "resolution_criteria": ["No flicker during drag", "Status updates once"],
  "screenshots": [],
  "related_files": ["static/css/app.css"]
}
```

### BUG con screenshot
```json
{
  "severity": "low",
  "reproduction": "Enable dark mode and open Dashboard",
  "expected": "Pills aligned and centered",
  "root_cause": "CSS override on status-badge affecting line-height",
  "resolution_criteria": ["Pills baseline aligned", "No overlap with icons"],
  "screenshots": [
    "http://127.0.0.1:8000/static/uploads/bugs/bug-screenshot-ui.png"
  ],
  "related_files": []
}
```

### TODO
```json
{
  "kind": "feature",
  "reproduction": "optional steps",
  "acceptance_criteria": ["criterion 1", "criterion 2"],
  "dependencies": [],
  "priority": "p2",
  "related_files": ["utils/items.py", "static/js/tabs/memory.js"],
  "done_summary": "describe what was implemented and why so that the reviewer can understand the approach"
}
```

## Reglas al resolver (enforcement)
- Al cambiar el estado a `resolved`:
  - bug/todo deben incluir `meta.done_summary` (≥120 caracteres) y al menos un elemento en `meta.related_files`.
  - La UI muestra un modal para completar estos campos si faltan al mover una tarjeta a Resolved.
  - El backend valida estos requisitos y devuelve error si no se cumplen.

## Screenshots y logs
- Capturas: usa MCP Chrome DevTools para tomar un PNG del viewport y guárdalo en `static/uploads/bugs/<slug>.png`.
- URL pública servida por la app: `http://127.0.0.1:8000/static/uploads/bugs/<slug>.png`.
- Incluir la URL en `meta.screenshots` es muy recomendable cuando el bug es visual.
- Si no procede captura, añade `logs_excerpt` con el extracto mínimo útil de los logs.

## Errores de validación (ejemplo)
- `meta inválido para 'bug': faltan campos: reproduction, expected, root_cause; valores inválidos: severity: Input should be 'high' | 'medium' | 'low'.`
- Solución: completa los campos faltantes y ajusta los valores a los permitidos.
