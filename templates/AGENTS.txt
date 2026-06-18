# Repository Guidelines

## Project Overview

Contextarium is a local-first FastAPI application that exposes a web panel and an MCP-compatible HTTP endpoint for agent memory, project docs, bugs, todos, and RAG search.

The application starts from `app.py`. Shared implementation code lives in `utils/`, MCP wiring lives in `mcp_server/`, UI templates live in `templates/`, and static frontend assets live in `static/`.

## Workflow

- Before changing code, review the affected flow and the relevant guide in `Extra/Guias/`.
- Keep changes scoped to the user-facing behavior or bug being addressed.
- Prefer existing modules and patterns over new abstractions.
- Do not commit generated runtime state, local databases, model caches, uploads, logs, or secrets.

## Validation

- Add or update tests in `test/` for behavior changes.
- Run focused tests while iterating.
- Run `python -m pytest` before considering a change ready.
- Do not start long-running processes in automation. If a persistent process is required for manual verification, document the command instead.

## Coding Style

- Use 4-space indentation, snake_case names, and uppercase constants.
- Add typing where it clarifies interfaces.
- Keep visible UI text, code comments, and guide documents in English.
- Configure behavior through YAML or environment variables; do not hardcode secrets.
- Keep files reasonably small and split modules before they become difficult to review.

## Documentation

- Update `README.md` for public-facing setup or behavior changes.
- Update or add guides under `Extra/Guias/` for operational, MCP, RAG, storage, or UI changes.
- Keep examples generic and free of private project names or credentials.

## Security

- Treat Contextarium as local-only unless authentication and network restrictions are added.
- Never commit `.env`, `data/`, `.cache/`, `.duckdb/`, `static/uploads/*`, or `*.log`.
- Redact secrets from logs, test fixtures, screenshots, and issue reports.

## Pull Requests

- Use concise Conventional Commit-style titles when possible.
- Describe the problem, solution, tests run, and operational risks.
- Mention required DB rebuilds, config changes, or new environment variables.
