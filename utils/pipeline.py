"""
Pipeline de ingesta que construye la base de datos RAG desde un sitemap.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Optional

from tqdm import tqdm

from utils.chunking import chunk_document
from utils.config import AppConfig
from utils.crawling import crawl_sitemap
from utils.database import ChunkRow, DocumentRow, DuckDBManager
from utils.embeddings import EmbeddingProvider


@dataclass
class IngestionSummary:
    documents: int
    chunks: int


def rebuild_rag_from_sitemap(
    sitemap_url: str,
    config: AppConfig,
    embedder: Optional[EmbeddingProvider] = None,
) -> IngestionSummary:
    embedder = embedder or EmbeddingProvider(config.embeddings)

    crawled_docs = crawl_sitemap(sitemap_url, config.crawling)
    if not crawled_docs:
        raise RuntimeError("No se recuperaron páginas desde el sitemap.")

    print(f"Documentos crawlerados: {len(crawled_docs)}")

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

    if len(embeddings) != len(chunk_payload):
        raise RuntimeError("Faltan vectores de embeddings para completar la ingesta.")

    embedding_dim = embedder.embedding_dim

    print("Embeddings generados. Inicializando base de datos DuckDB...")

    manager = DuckDBManager(config.database, embedding_dim)
    manager.reset()
    manager.initialize_schema()

    print("Insertando documentos y chunks en DuckDB...")

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

    manager.teardown()

    return IngestionSummary(documents=len(doc_rows), chunks=len(chunk_rows))
