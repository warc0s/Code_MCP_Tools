"""
Pipeline de ingesta que construye la base de datos RAG a partir de distintas fuentes.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable, Optional

from tqdm import tqdm

from utils.chunking import chunk_document
from utils.config import AppConfig
from utils.crawling import CrawledDocument, crawl_sitemap, crawl_url_list
from utils.database import ChunkRow, DocumentRow, DuckDBManager
from utils.embeddings import EmbeddingProvider


@dataclass
class IngestionSummary:
    documents: int
    chunks: int


ProgressCallback = Callable[[dict], None]


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _wal_path(db_path: Path) -> Path:
    return Path(f"{db_path}.wal")


def _replace_database_atomically(staging_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = destination_path.with_name(f".{destination_path.name}.{uuid.uuid4().hex}.bak")
    backup_wal_path = _wal_path(backup_path)
    destination_wal_path = _wal_path(destination_path)
    staging_wal_path = _wal_path(staging_path)
    moved_destination = False
    moved_destination_wal = False
    moved_staging = False
    moved_staging_wal = False

    try:
        if destination_path.exists():
            os.replace(destination_path, backup_path)
            moved_destination = True
        if destination_wal_path.exists():
            os.replace(destination_wal_path, backup_wal_path)
            moved_destination_wal = True

        os.replace(staging_path, destination_path)
        moved_staging = True
        if staging_wal_path.exists():
            os.replace(staging_wal_path, destination_wal_path)
            moved_staging_wal = True
    except Exception:
        if moved_destination or moved_staging:
            _remove_file(destination_path)
        if moved_destination_wal or moved_staging_wal:
            _remove_file(destination_wal_path)
        if moved_destination and backup_path.exists():
            os.replace(backup_path, destination_path)
        if moved_destination_wal and backup_wal_path.exists():
            os.replace(backup_wal_path, destination_wal_path)
        raise
    else:
        _remove_file(backup_path)
        _remove_file(backup_wal_path)
    finally:
        _remove_file(staging_path)
        _remove_file(staging_wal_path)


def _rebuild_rag_from_crawled_documents(
    crawled_docs: Iterable[CrawledDocument],
    config: AppConfig,
    embedder: EmbeddingProvider,
    progress_cb: Optional[ProgressCallback] = None,
) -> IngestionSummary:
    crawled_docs = list(crawled_docs)
    if not crawled_docs:
        raise RuntimeError("No se recuperaron páginas para la ingesta.")

    print(f"Documentos crawlerados: {len(crawled_docs)}")
    if progress_cb:
        progress_cb({"stage": "chunking", "documents": len(crawled_docs)})

    doc_rows: list[DocumentRow] = []
    chunk_payload: list[dict] = []
    seen_chunk_fingerprints: set[str] = set()

    for doc in crawled_docs:
        doc_id = uuid.uuid4().hex
        doc_rows.append(
            DocumentRow(
                doc_id=doc_id,
                url=doc.url,
                title=doc.title,
                fingerprint=doc.fingerprint,
            )
        )

        chunks = chunk_document(doc.markdown, config.chunking)
        for chunk in chunks:
            fingerprint = chunk["fingerprint"]
            if fingerprint in seen_chunk_fingerprints:
                continue
            seen_chunk_fingerprints.add(fingerprint)
            chunk_payload.append(
                {
                    "doc_id": doc_id,
                    "section_path": chunk["section_path"],
                    "position": int(chunk["position"]),
                    "text": chunk["text"],
                    "fingerprint": fingerprint,
                }
            )

    if not chunk_payload:
        raise RuntimeError("No se generaron chunks tras el proceso de chunking.")

    print(f"Chunks únicos listos para embebido: {len(chunk_payload)}")
    if progress_cb:
        progress_cb(
            {
                "stage": "embedding",
                "documents": len(crawled_docs),
                "chunks": len(chunk_payload),
                "total": len(chunk_payload),
                "done": 0,
            }
        )

    texts = [payload["text"] for payload in chunk_payload]
    embeddings: list[list[float]] = []
    batch_size = max(1, getattr(config.embeddings, "batch_size", 64))
    with tqdm(total=len(texts), desc="Embeddings", unit="chunk") as progress:
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            batch_vectors = embedder.embed_documents(batch)
            if len(batch_vectors) != len(batch):
                raise RuntimeError("El proveedor de embeddings devolvió un lote con longitud inesperada.")
            embeddings.extend(batch_vectors)
            progress.update(len(batch_vectors))
            if progress_cb:
                progress_cb(
                    {
                        "stage": "embedding",
                        "documents": len(crawled_docs),
                        "chunks": len(chunk_payload),
                        "total": len(chunk_payload),
                        "done": len(embeddings),
                    }
                )

    if len(embeddings) != len(chunk_payload):
        raise RuntimeError("Faltan vectores de embeddings para completar la ingesta.")

    embedding_dim = embedder.embedding_dim

    print("Embeddings generados. Inicializando base de datos DuckDB...")
    if progress_cb:
        progress_cb(
            {
                "stage": "duckdb_init",
                "documents": len(crawled_docs),
                "chunks": len(chunk_payload),
                "total": len(chunk_payload),
                "done": len(chunk_payload),
            }
        )

    destination_path = Path(config.database.path)
    staging_path = destination_path.with_name(f".{destination_path.name}.{uuid.uuid4().hex}.tmp")
    staging_database = replace(config.database, path=staging_path)
    manager = DuckDBManager(staging_database, embedding_dim)
    build_completed = False
    try:
        manager.reset()
        manager.initialize_schema()

        print("Insertando documentos y chunks en DuckDB...")
        if progress_cb:
            progress_cb(
                {
                    "stage": "duckdb_insert",
                    "documents": len(crawled_docs),
                    "chunks": len(chunk_payload),
                    "total": len(chunk_payload),
                    "done": len(chunk_payload),
                }
            )

        chunk_rows: list[ChunkRow] = []
        for payload, vector in zip(chunk_payload, embeddings):
            chunk_id = hashlib.sha256(
                f"{payload['doc_id']}::{payload['position']}::{payload['fingerprint']}".encode("utf-8")
            ).hexdigest()
            chunk_rows.append(
                ChunkRow(
                    chunk_id=chunk_id,
                    doc_id=payload["doc_id"],
                    section_path=payload["section_path"],
                    position=payload["position"],
                    text=payload["text"],
                    fingerprint=payload["fingerprint"],
                    embedding=vector,
                )
            )

        manager.insert_documents(doc_rows)
        manager.insert_chunks(chunk_rows)
        # Crear índices pesados tras la carga para evitar mantenimiento incremental por fila
        manager.create_indexes()
        if progress_cb:
            progress_cb(
                {
                    "stage": "done",
                    "documents": len(doc_rows),
                    "chunks": len(chunk_rows),
                    "total": len(chunk_payload),
                    "done": len(chunk_payload),
                }
            )

        reranker_model = (
            config.reranker.model_name
            if config.main.mode == "local"
            else config.reranker.cloud_model_name or config.reranker.model_name
        )
        manager.write_metadata(
            {
                "runtime_mode": config.main.mode,
                "embedding_model_name": embedder.model_name,
                "embedding_dim": str(embedding_dim),
                "reranker_model_name": reranker_model,
            }
        )
        build_completed = True
    finally:
        manager.teardown()
        if not build_completed:
            _remove_file(staging_path)
            _remove_file(_wal_path(staging_path))

    _replace_database_atomically(staging_path, destination_path)

    return IngestionSummary(documents=len(doc_rows), chunks=len(chunk_rows))


def rebuild_rag_from_sitemap(
    sitemap_url: str,
    config: AppConfig,
    embedder: Optional[EmbeddingProvider] = None,
    progress_cb: Optional[ProgressCallback] = None,
) -> IngestionSummary:
    embedder = embedder or EmbeddingProvider(config.embeddings, mode=config.main.mode)
    crawled_docs = crawl_sitemap(sitemap_url, config.crawling)
    return _rebuild_rag_from_crawled_documents(crawled_docs, config, embedder, progress_cb=progress_cb)


def rebuild_rag_from_urls(
    urls: Iterable[str],
    config: AppConfig,
    embedder: Optional[EmbeddingProvider] = None,
    progress_cb: Optional[ProgressCallback] = None,
) -> IngestionSummary:
    embedder = embedder or EmbeddingProvider(config.embeddings, mode=config.main.mode)
    crawled_docs = crawl_url_list(list(urls), config.crawling)
    return _rebuild_rag_from_crawled_documents(crawled_docs, config, embedder, progress_cb=progress_cb)
