# Meta By Type (Memory/Docs/Bugs/Todos)

This guide describes the `meta` structure for each item type, validation rules, and practical examples.

## Summary

- Validation: `meta` is validated with Pydantic per type, but all of its fields are optional extras. Required fields moved to `typed` (per type), and are validated on creation and when applicable.
- MCP tools (`store_item`, `update_item`): expose optional `meta` and per-type required `typed` in their JSON Schema.
- UI: the `meta` template is auto-applied when switching subtabs; `typed` fields are shown as dedicated inputs per type.

## Fields By Type

- memory (required typed fields)
  - topic (str)
  - decision (str)
  - context (str)
  - rationale (str)
  - related_links (list[str], optional)
- doc (optional typed fields)
  - authors (list[str])
  - related_docs (list[str])
  - source_url, version_notes -> optional `meta`
- bug (required typed fields)
  - severity: "high" | "medium" | "low"
  - reproduction (str; exact steps)
  - expected (str)
  - root_cause (str)
  - extras (optional meta): logs_excerpt, resolution_criteria (list), related_files (list), done_summary (resolution summary)
- todo (required typed fields)
  - kind: "bug_fix" | "refactor" | "feature" | "chore"
  - acceptance_criteria (list[str])
  - priority: "p0" | "p1" | "p2"
  - extras (optional meta): reproduction, dependencies, related_files, done_summary
  - done_summary (str, optional; required when resolving, >=120 chars)

## Examples

### BUG With Logs

```json
{
  "severity": "medium",
  "reproduction": "Open Memory -> Todo, drag card quickly",
  "expected": "Single update to target status without flicker",
  "root_cause": "DOM reflow under heavy drag events",
  "logs_excerpt": "Console shows duplicate drop event; network quiet; no 500s",
  "done_summary": "explain the implemented change, rationale and how it fixes the issue. Include relevant context and trade-offs so that future readers understand the approach.",
  "resolution_criteria": ["No flicker during drag", "Status updates once"],
  "related_files": ["static/css/app.css"]
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

## Resolution Enforcement

- When changing status to `resolved`:
  - bug/todo must include `meta.done_summary` (>=120 chars) and at least one entry in `meta.related_files`.
  - The UI shows a modal to complete those fields when they are missing while moving a card to Resolved.
  - The backend validates these requirements and returns an error when they are not met.

## Validation Errors (Example)

- `invalid meta for 'bug': missing fields: reproduction, expected, root_cause; invalid values: severity: Input should be 'high' | 'medium' | 'low'.`
- Fix: complete the missing fields and adjust values to the allowed set.
