from __future__ import annotations

from typing import List, Literal, Optional, Union, Dict, Any

from pydantic import BaseModel, Field, ValidationError


# Optional meta (advanced/extras). All fields optional; required fields are now typed per-type.
class MemoryMeta(BaseModel):
    model_config = {"extra": "allow"}
    topic: Optional[str] = None
    decision: Optional[str] = None
    context: Optional[str] = None
    rationale: Optional[str] = None
    related_links: List[str] = Field(default_factory=list)


class DocMeta(BaseModel):
    model_config = {"extra": "allow"}
    authors: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    related_docs: List[str] = Field(default_factory=list)
    version_notes: Optional[str] = None


class BugMeta(BaseModel):
    model_config = {"extra": "allow"}
    severity: Optional[Literal["high", "medium", "low"]] = None
    reproduction: Optional[str] = None
    logs_excerpt: Optional[str] = None
    expected: Optional[str] = None
    root_cause: Optional[str] = None
    fix_summary: Optional[str] = None
    # New optional field used when resolving: high-level summary of the fix
    done_summary: Optional[str] = None
    fixed_in_commit: Optional[str] = None
    resolution_criteria: List[str] = Field(default_factory=list)
    screenshots: List[str] = Field(default_factory=list)
    related_files: List[str] = Field(default_factory=list)


class TodoMeta(BaseModel):
    model_config = {"extra": "allow"}
    kind: Optional[Literal["bug_fix", "refactor", "feature", "chore"]] = None
    reproduction: Optional[str] = None
    acceptance_criteria: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    priority: Optional[Literal["p0", "p1", "p2"]] = None
    related_files: List[str] = Field(default_factory=list)
    # New optional field used when resolving: high-level summary of the implementation
    done_summary: Optional[str] = None


def _format_validation_errors(e: ValidationError) -> str:
    errs = e.errors()
    missing = []
    invalid = []
    for err in errs:
        loc = ".".join(str(x) for x in err.get("loc", [])) or "(root)"
        etype = err.get("type", "")
        msg = err.get("msg", "invalid value")
        if etype == "missing":
            missing.append(loc)
        else:
            invalid.append((loc, msg))
    parts = []
    if missing:
        parts.append(f"missing fields: {', '.join(missing)}")
    if invalid:
        parts.append("invalid values: " + "; ".join(f"{loc}: {msg}" for loc, msg in invalid))
    return "; ".join(parts) or "invalid meta"


def validate_meta(item_type: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    t = (item_type or "").strip().lower()
    try:
        if t == "memory":
            return MemoryMeta(**(meta or {})).model_dump()
        if t == "doc":
            return DocMeta(**(meta or {})).model_dump()
        if t == "bug":
            return BugMeta(**(meta or {})).model_dump()
        if t == "todo":
            return TodoMeta(**(meta or {})).model_dump()
    except ValidationError as e:
        detail = _format_validation_errors(e)
        raise ValueError(
            f"Invalid meta for '{t}': {detail}. Check the Suggested fields in the UI or use the auto-applied template."
        ) from e
    raise ValueError("Unsupported item type for meta validation.")


# Typed required fields models
class MemoryRequired(BaseModel):
    topic: str
    decision: str
    context: str
    rationale: str
    related_links: List[str] = Field(default_factory=list)


class DocRequired(BaseModel):
    # No hard-required fields for doc; keep optional typed
    authors: List[str] = Field(default_factory=list)
    related_docs: List[str] = Field(default_factory=list)


class BugRequired(BaseModel):
    severity: Literal["high", "medium", "low"]
    reproduction: str
    expected: str
    root_cause: str


class TodoRequired(BaseModel):
    kind: Literal["bug_fix", "refactor", "feature", "chore"]
    acceptance_criteria: List[str]
    priority: Literal["p0", "p1", "p2"]


def validate_typed_required(item_type: str, typed: Dict[str, Any]) -> Dict[str, Any]:
    t = (item_type or "").strip().lower()
    if t == "memory":
        return MemoryRequired(**(typed or {})).model_dump()
    if t == "doc":
        # doc typed fields are optional; normalize
        return DocRequired(**(typed or {})).model_dump()
    if t == "bug":
        return BugRequired(**(typed or {})).model_dump()
    if t == "todo":
        return TodoRequired(**(typed or {})).model_dump()
    raise ValueError("Unsupported item type for typed validation.")


def typed_json_schema(item_type: str, required: bool = True) -> Dict[str, Any]:
    """Return JSON Schema for the `typed` object for a given item type.

    - When `required=True`, the schema includes required keys for types that enforce them.
    - When `required=False`, the schema accepts partial updates (used by update_item).
    """
    t = (item_type or "").strip().lower()
    if t == "memory":
        props = {
            "topic": {"type": "string"},
            "decision": {"type": "string"},
            "context": {"type": "string"},
            "rationale": {"type": "string"},
            "related_links": {"type": "array", "items": {"type": "string"}},
        }
        schema: Dict[str, Any] = {"type": "object", "properties": props}
        if required:
            schema["required"] = ["topic", "decision", "context", "rationale"]
        return schema
    if t == "doc":
        props = {
            "authors": {"type": "array", "items": {"type": "string"}},
            "related_docs": {"type": "array", "items": {"type": "string"}},
        }
        return {"type": "object", "properties": props}
    if t == "bug":
        props = {
            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
            "reproduction": {"type": "string"},
            "expected": {"type": "string"},
            "root_cause": {"type": "string"},
        }
        schema = {"type": "object", "properties": props}
        if required:
            schema["required"] = ["severity", "reproduction", "expected", "root_cause"]
        return schema
    if t == "todo":
        props = {
            "kind": {"type": "string", "enum": ["bug_fix", "refactor", "feature", "chore"]},
            "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
            "priority": {"type": "string", "enum": ["p0", "p1", "p2"]},
        }
        schema = {"type": "object", "properties": props}
        if required:
            schema["required"] = ["kind", "acceptance_criteria", "priority"]
        return schema
    raise ValueError("Unsupported item type for typed schema.")


def typed_json_schema_oneof(required: bool = True) -> Dict[str, Any]:
    return {
        "oneOf": [
            {"title": "memory", **typed_json_schema("memory", required=required)},
            {"title": "doc", **typed_json_schema("doc", required=required)},
            {"title": "bug", **typed_json_schema("bug", required=required)},
            {"title": "todo", **typed_json_schema("todo", required=required)},
        ]
    }


def meta_json_schema(item_type: str) -> Dict[str, Any]:
    t = (item_type or "").strip().lower()
    if t == "memory":
        return MemoryMeta.model_json_schema()
    if t == "doc":
        return DocMeta.model_json_schema()
    if t == "bug":
        return BugMeta.model_json_schema()
    if t == "todo":
        return TodoMeta.model_json_schema()
    raise ValueError("Unsupported item type for meta schema.")


def meta_json_schema_oneof() -> Dict[str, Any]:
    # Combined oneOf schema used in MCP tool JSON Schema
    return {
        "oneOf": [
            {"title": "memory", **MemoryMeta.model_json_schema() },
            {"title": "doc", **DocMeta.model_json_schema() },
            {"title": "bug", **BugMeta.model_json_schema() },
            {"title": "todo", **TodoMeta.model_json_schema() },
        ]
    }


__all__ = [
    "MemoryMeta",
    "DocMeta",
    "BugMeta",
    "TodoMeta",
    "validate_meta",
    "meta_json_schema",
    "meta_json_schema_oneof",
    "validate_typed_required",
    "typed_json_schema",
    "typed_json_schema_oneof",
]
