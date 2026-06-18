# Contributing

Thanks for improving Contextarium.

## Development Setup

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Copy the environment template if you need cloud providers:

```bash
cp .env.example .env
```

## Validation

Run focused tests for documentation and public-release hygiene:

```bash
python -m pytest test/test_docs_consistency.py test/test_branding_contextarium.py test/test_public_release_readiness.py
```

Run the full suite before opening a pull request:

```bash
python -m pytest
```

## Documentation

When changing behavior that affects users, MCP tools, storage, or operations, update the relevant guide in `Extra/Guias/`.

Keep visible UI text, code comments, and guide documents in English.

## Security

Do not commit `.env`, databases, model caches, uploads, logs, or private corpora. See `SECURITY.md`.

## Pull Requests

Use concise Conventional Commit-style titles when possible, for example:

```text
fix: harden project deletion guard
docs: clarify cloud embedding setup
```

Describe:

- Problem.
- Solution.
- Tests run.
- Operational risks such as config changes, DB rebuilds, or new environment variables.

Use `.github/PULL_REQUEST_TEMPLATE.md` as the checklist for public-release hygiene.
