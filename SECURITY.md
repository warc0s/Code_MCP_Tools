# Security Policy

## Supported Use

Contextarium is a local developer tool. The web UI and MCP endpoint do not include built-in authentication.

Run it on localhost or a trusted private network. If you expose it beyond that boundary, put it behind authentication, TLS, and network access controls.

## Sensitive Local Data

Do not publish or commit local runtime state:

- `.env` and other environment files.
- `data/` databases.
- `.cache/` model caches.
- `.duckdb/` extension caches.
- `static/uploads/` attachments or screenshots.
- `*.log` files.

## Reporting Vulnerabilities

Use GitHub private vulnerability reporting if it is enabled for the repository. If it is not enabled, contact the maintainers through a private channel before opening a public issue.

Please include:

- Affected version or commit.
- Exact steps to reproduce.
- Expected and observed behavior.
- Relevant logs with secrets removed.
- Impact assessment and any known workaround.

## Deployment Guidance

- Keep `APP_HOST=127.0.0.1` for local-only use.
- Treat Docker port mappings as public exposure unless your host firewall restricts access.
- Review enabled MCP tools before sharing the endpoint.
- Do not mount secrets or private corpora into containers that will be published or shared.
