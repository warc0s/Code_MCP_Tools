from __future__ import annotations

from pathlib import Path

import yaml


def test_public_release_docs_and_logo_exist() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    required_sections = [
        "## Table Of Contents",
        "## Quick Start",
        "## Configuration",
        "## MCP Integrations",
        "## Security And Privacy",
        "## License",
    ]
    for section in required_sections:
        assert section in readme

    logo = Path("static/img/contextarium-logo.svg")
    assert logo.exists()
    assert "Contextarium logo" in logo.read_text(encoding="utf-8")
    assert "static/img/contextarium-logo.svg" in readme
    assert "Apache--2.0" in readme
    assert "See `LICENSE`" in readme


def test_license_file_is_apache_2() -> None:
    license_text = Path("LICENSE").read_text(encoding="utf-8")

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "Copyright 2026 Contextarium contributors" in license_text


def test_public_configs_are_neutral() -> None:
    for path in [Path("config.yaml"), Path("config.example.yaml")]:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["ui"]["selected_project"] is None
        assert data["database"]["path"] == "data/rag.duckdb"
        assert data["memory_database"]["path"] == "data/memory.sqlite3"


def test_public_hygiene_files_cover_sensitive_runtime_state() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    for pattern in ["data/", ".duckdb/", ".cache/", ".cache/models/", "static/uploads/*", "*.log"]:
        assert pattern in gitignore

    for pattern in [".git/", ".env", ".env.*", "data/", ".duckdb/", ".cache/", "static/uploads/*"]:
        assert pattern in dockerignore


def test_github_publication_metadata_exists() -> None:
    required = [
        Path(".github/workflows/public-readiness.yml"),
        Path(".github/ISSUE_TEMPLATE/bug_report.md"),
        Path(".github/ISSUE_TEMPLATE/feature_request.md"),
        Path(".github/PULL_REQUEST_TEMPLATE.md"),
    ]

    for path in required:
        assert path.exists(), path

    workflow = Path(".github/workflows/public-readiness.yml").read_text(encoding="utf-8")
    assert "test/test_public_release_readiness.py" in workflow
    assert "python-version: \"3.12\"" in workflow


def test_base_template_uses_local_assets_only() -> None:
    base = Path("templates/base.html").read_text(encoding="utf-8")

    assert "img/contextarium-logo.svg" in base
