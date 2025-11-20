"""
Gestión de configuración de la aplicación.

La configuración se centraliza en `config.yaml`, se valida con dataclasses
tipadas y se expone como un objeto inmutable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass(frozen=True)
class MainConfig:
    mode: str = "local"

    def __post_init__(self) -> None:
        normalized = (self.mode or "local").strip().lower()
        if normalized not in {"local", "cloud"}:
            raise ValueError("El modo principal debe ser 'local' o 'cloud'.")
        object.__setattr__(self, "mode", normalized)


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path = Path("data/rag.duckdb")


@dataclass(frozen=True)
class CrawlingConfig:
    workers: int = 8
    pattern: str = "*"
    max_urls: int = -1
    cache_mode: str = "enabled"


@dataclass(frozen=True)
class ChunkingConfig:
    max_tokens: int = 400
    overlap_tokens: int = 80
    min_chunk_tokens: int = 120
    preserve_code_blocks: bool = True
    respect_headings: bool = True


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    normalize_embeddings: bool = True
    query_prompt_name: Optional[str] = "query"
    embedding_dim: Optional[int] = None
    cloud_model_name: Optional[str] = None


@dataclass(frozen=True)
class RetrievalConfig:
    dense_topk: int = 20
    lexical_topk: int = 20
    hybrid_alpha: float = 0.5
    mmr_lambda: float = 0.5
    same_url_penalty: float = 0.08
    final_k: int = 8
    force_english_queries: bool = True
    rerank_topk: int = 12
    enable_rerank: bool = False


@dataclass(frozen=True)
class RerankerConfig:
    model_name: str = "Qwen/Qwen3-Reranker-0.6B"
    max_length: int = 8192
    cloud_model_name: Optional[str] = None


@dataclass(frozen=True)
class PolicyConfig:
    force_english_queries: bool = True


@dataclass(frozen=True)
class MCPConfig:
    tools: Dict[str, bool] = field(default_factory=dict)
    tool_sets: Dict[str, Dict[str, bool]] = field(default_factory=dict)
    active_set: Optional[str] = None


@dataclass(frozen=True)
class AppConfig:
    main: MainConfig = field(default_factory=MainConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    crawling: CrawlingConfig = field(default_factory=CrawlingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)

    @staticmethod
    def _build_dataclass(dataclass_type, data: Dict[str, Any]):
        return dataclass_type(
            **{k: v for k, v in data.items() if k in dataclass_type.__dataclass_fields__}
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        def get_section(name: str, klass):
            section = data.get(name, {})
            if isinstance(section, str) and "mode" in klass.__dataclass_fields__:
                section = {"mode": section}
            if not isinstance(section, dict):
                raise ValueError(f"La sección '{name}' debe ser un objeto.")
            return cls._build_dataclass(klass, section) if section else klass()

        return cls(
            main=get_section("main", MainConfig),
            database=get_section("database", DatabaseConfig),
            crawling=get_section("crawling", CrawlingConfig),
            chunking=get_section("chunking", ChunkingConfig),
            embeddings=get_section("embeddings", EmbeddingConfig),
            retrieval=get_section("retrieval", RetrievalConfig),
            reranker=get_section("reranker", RerankerConfig),
            policy=get_section("policy", PolicyConfig),
            mcp=get_section("mcp", MCPConfig),
        )

    @classmethod
    def load(cls, path: Path | str = "config.yaml") -> "AppConfig":
        location = Path(path)
        if not location.exists():
            raise FileNotFoundError(f"No se encontró el archivo de configuración: {location}")
        data = yaml.safe_load(location.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("El archivo de configuración debe contener un objeto YAML de primer nivel.")
        return cls.from_dict(data)


__all__ = [
    "AppConfig",
    "ChunkingConfig",
    "CrawlingConfig",
    "DatabaseConfig",
    "EmbeddingConfig",
    "MCPConfig",
    "MainConfig",
    "PolicyConfig",
    "RetrievalConfig",
    "RerankerConfig",
]
