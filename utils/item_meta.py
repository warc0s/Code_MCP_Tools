from __future__ import annotations

from typing import List, Literal, Optional, Union, Dict, Any

from pydantic import BaseModel, Field, ValidationError


class MemoryMeta(BaseModel):
    model_config = {"extra": "allow"}
    topic: str
    decision: str
    context: str
    rationale: str
    related_links: List[str] = Field(default_factory=list)


class DocMeta(BaseModel):
    model_config = {"extra": "allow"}
    authors: List[str] = Field(default_factory=list)
    source_url: Optional[str] = ""
    related_docs: List[str] = Field(default_factory=list)
    version_notes: Optional[str] = ""


class BugMeta(BaseModel):
    model_config = {"extra": "allow"}
    severity: Literal["high", "medium", "low"]
    reproduction: str
    logs_excerpt: Optional[str] = None
    expected: str
    root_cause: str
    fix_summary: Optional[str] = None
    fixed_in_commit: Optional[str] = None
    resolution_criteria: List[str] = Field(default_factory=list)
    screenshots: List[str] = Field(default_factory=list)
    related_files: List[str] = Field(default_factory=list)


class TodoMeta(BaseModel):
    model_config = {"extra": "allow"}
    kind: Literal["bug_fix", "refactor", "feature", "chore"]
    reproduction: Optional[str] = None
    acceptance_criteria: List[str]
    dependencies: List[str] = Field(default_factory=list)
    priority: Literal["p0", "p1", "p2"]
    related_files: List[str] = Field(default_factory=list)


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
        parts.append(f"faltan campos: {', '.join(missing)}")
    if invalid:
        parts.append("valores inválidos: " + "; ".join(f"{loc}: {msg}" for loc, msg in invalid))
    return "; ".join(parts) or "meta inválido"


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
        raise ValueError(f"meta inválido para '{t}': {detail}. Revisa los Suggested fields de la UI o usa la plantilla automáticamente aplicada.") from e
    raise ValueError("Unsupported item type for meta validation.")


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
]
