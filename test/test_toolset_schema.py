from __future__ import annotations

import sys
from pathlib import Path as _Path

# Ensure repository root in sys.path for local imports
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from mcp_server.toolset import RAGToolset


def test_toolset_declares_output_schema():
    # No retriever or item service: inspect only the catalog.
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    tools = ts.list_tools()
    assert isinstance(tools, dict) and tools
    # At least one tool should declare output_schema (for example, hybrid_search).
    assert any("output_schema" in spec for spec in tools.values())


def test_hybrid_search_description_recommends_top_k():
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    tools = ts.list_tools()
    assert "hybrid_search" in tools
    desc = tools["hybrid_search"].get("description", "")
    assert "Recommended top_k" in desc
    assert "6" in desc
    assert "Do not call in parallel" in desc


def test_store_item_schema_correlates_type_to_typed_and_meta():
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    tools = ts.list_tools()
    schema = tools["store_item"]["schema"]
    assert schema.get("type") == "object"
    all_of = schema.get("allOf")
    assert isinstance(all_of, list) and all_of, "store_item schema must include allOf rules"

    seen: set[str] = set()
    for rule in all_of:
        t = (
            (rule.get("if") or {})
            .get("properties", {})
            .get("type", {})
            .get("const")
        )
        if not t:
            continue
        seen.add(t)
        then = rule.get("then") or {}
        props = then.get("properties") or {}
        assert "typed" in props and "meta" in props
        if t in {"memory", "bug", "todo"}:
            assert "typed" in (then.get("required") or [])

    assert {"memory", "doc", "bug", "todo"}.issubset(seen)


def test_update_item_schema_supports_optional_type_hint():
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    tools = ts.list_tools()
    schema = tools["update_item"]["schema"]
    fields = schema.get("properties", {}).get("fields", {})
    assert fields.get("type") == "object"
    assert "type" in (fields.get("properties") or {}), "fields.type should exist as an optional hint"
    all_of = fields.get("allOf")
    assert isinstance(all_of, list) and all_of, "update_item fields should include allOf rules"


def test_toolset_runtime_schema_rejects_conditional_typed_shape():
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    schema = ts.list_tools()["store_item"]["schema"]

    try:
        ts._validate(schema, {"type": "memory", "title": "Bad", "typed": "not-an-object"})
    except ValueError as exc:
        assert "typed" in str(exc)
    else:
        raise AssertionError("invalid typed payload should be rejected")


def test_toolset_runtime_schema_rejects_bool_for_integer():
    ts = RAGToolset(retriever=None, enabled_tools=None, cli_logs_enabled=False)
    schema = ts.list_tools()["dense_search"]["schema"]

    try:
        ts._validate(schema, {"query": "alpha", "top_k": True})
    except ValueError as exc:
        assert "top_k" in str(exc)
    else:
        raise AssertionError("bool must not be accepted as an integer")
