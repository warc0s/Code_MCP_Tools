"""
Herramientas de búsqueda sobre DuckDB para el RAG.
"""

from __future__ import annotations

import logging
import math
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional

from utils.config import RetrievalConfig
from utils.embeddings import EmbeddingProvider
from utils.reranker import PassageReranker


def _cosine_similarity(vec_a: Iterable[float], vec_b: Iterable[float]) -> float:
    a = list(vec_a or [])
    b = list(vec_b or [])
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


logger = logging.getLogger(__name__)


class Retriever:
    def __init__(
        self,
        connection,
        config: RetrievalConfig,
        embedder: EmbeddingProvider,
        reranker: Optional[PassageReranker] = None,
    ):
        self.connection = connection
        self.config = config
        self.embedder = embedder
        self.reranker = reranker
        self._fts_available: Optional[bool] = None

    def _check_fts_available(self) -> bool:
        if self._fts_available is not None:
            return self._fts_available
        try:
            row = self.connection.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'fts_main_chunks' LIMIT 1;"
            ).fetchone()
            self._fts_available = bool(row)
        except Exception:
            self._fts_available = False
        if not self._fts_available:
            logger.info("FTS no disponible; se usará fallback léxico basado en LIKE.")
        return self._fts_available

    def _ensure_query(self, query: str) -> str:
        cleaned = (query or "").strip()
        if not cleaned:
            logger.warning("Se recibió una consulta vacía.")
            raise ValueError("La consulta no puede estar vacía.")
        if self.config.force_english_queries and not cleaned.isascii():
            logger.warning("Consulta rechazada por no ser ASCII: %s", query)
            raise ValueError("Esta base espera consultas en inglés para mantener la calidad del RAG.")
        logger.debug("Consulta normalizada: %s", cleaned)
        return cleaned

    def _normalize(self, candidates: List[Dict[str, Any]]) -> Dict[str, float]:
        scores = [float(c["score"]) for c in candidates if c.get("score") is not None]
        if not scores:
            return {}
        min_score = min(scores)
        max_score = max(scores)
        if math.isclose(min_score, max_score):
            return {c["chunk_id"]: 1.0 for c in candidates}
        return {
            c["chunk_id"]: (float(c["score"]) - min_score) / (max_score - min_score) for c in candidates
        }

    def _strip_internal(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cleaned: List[Dict[str, Any]] = []
        for item in candidates:
            payload = {k: v for k, v in item.items() if k not in {"embedding", "dense_norm", "lexical_norm"}}
            cleaned.append(payload)
        return cleaned

    def _generate_embeddings(self, query: str) -> List[float]:
        return self.embedder.embed_query(query)

    def _dense_candidates(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        top = top_k or self.config.dense_topk
        logger.debug("Búsqueda densa: query=%s, top_k=%s", query, top)
        try:
            vector = self._generate_embeddings(query)
        except Exception:
            logger.exception("Fallo generando embeddings para la consulta densa: %s", query)
            raise
        try:
            rows = self.connection.execute(
                """
                SELECT
                    c.chunk_id,
                    c.doc_id,
                    d.url,
                    d.title,
                    c.section_path,
                    c.position,
                    c.text,
                    1 - (c.embedding <-> ?) AS score,
                    c.embedding
                FROM chunks AS c
                JOIN docs AS d ON d.doc_id = c.doc_id
                ORDER BY c.embedding <-> ?
                LIMIT ?
                """,
                [vector, vector, top],
            ).fetchall()
        except Exception as exc:
            # Fallback robusto: si el operador vectorial no está disponible (p. ej., VSS no cargado),
            # calculamos similitud coseno en Python sobre una muestra acotada.
            logger.warning(
                "Fallo búsqueda densa con VSS; usando fallback en memoria (parcial): %s",
                exc,
            )
            sample_size = max(200, min(top * 50, 1000))
            try:
                sample_rows = self.connection.execute(
                    """
                    SELECT
                        c.chunk_id,
                        c.doc_id,
                        d.url,
                        d.title,
                        c.section_path,
                        c.position,
                        c.text,
                        c.embedding
                    FROM chunks AS c
                    JOIN docs AS d ON d.doc_id = c.doc_id
                    LIMIT ?
                    """,
                    [sample_size],
                ).fetchall()
            except Exception:
                logger.exception("Error ejecutando el fallback de búsqueda densa.")
                raise
            rows = []
            for row in sample_rows:
                (
                    chunk_id,
                    doc_id,
                    url,
                    title,
                    section_path,
                    position,
                    text,
                    embedding,
                ) = row
                score = _cosine_similarity(vector, list(embedding))
                rows.append(
                    (
                        chunk_id,
                        doc_id,
                        url,
                        title,
                        section_path,
                        position,
                        text,
                        score,
                        list(embedding),
                    )
                )
            # Ordenar por score y truncar al top
            rows = sorted(rows, key=lambda r: float(r[7]), reverse=True)[:top]
        candidates = []
        for row in rows:
            (
                chunk_id,
                doc_id,
                url,
                title,
                section_path,
                position,
                text,
                score,
                embedding,
            ) = row
            candidates.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "url": url,
                    "title": title,
                    "section_path": section_path,
                    "position": position,
                    "text": text,
                    "score": max(0.0, min(1.0, float(score))),
                    "embedding": list(embedding),
                }
            )
        if not candidates:
            logger.info("Búsqueda densa sin resultados para query=%s", query)
        return candidates

    def _lexical_candidates(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        top = top_k or self.config.lexical_topk
        logger.debug("Búsqueda léxica: query=%s, top_k=%s", query, top)
        rows: List[Any] = []
        if self._check_fts_available():
            try:
                rows = self.connection.execute(
                    """
                    SELECT
                        c.chunk_id,
                        c.doc_id,
                        d.url,
                        d.title,
                        c.section_path,
                        c.position,
                        c.text,
                        fts_main_chunks.score AS score,
                        c.embedding
                    FROM fts_main_chunks
                    JOIN chunks AS c ON c.rowid = fts_main_chunks.rowid
                    JOIN docs AS d ON d.doc_id = c.doc_id
                    WHERE fts_main_chunks.match_bm25(?)
                    ORDER BY bm25(fts_main_chunks) DESC
                    LIMIT ?
                    """,
                    [query, top],
                ).fetchall()
            except Exception:
                logger.warning("Error usando FTS para la consulta léxica; se usará fallback LIKE hasta reinicio.")
                self._fts_available = False
                rows = []
        if not rows:
            # Fallback: si FTS no está disponible, usar un ranking simple por coincidencias LIKE
            tokens = [t for t in (query or "").lower().split() if t]
            if not tokens:
                logger.info("Consulta léxica sin tokens tras normalización: %s", query)
                return []
            like_params = [f"%{t}%" for t in tokens]
            score_expr = " + ".join(["CASE WHEN lower(c.text) LIKE ? THEN 1 ELSE 0 END" for _ in tokens])
            where_expr = " OR ".join(["lower(c.text) LIKE ?" for _ in tokens])
            sql = f"""
                SELECT
                    c.chunk_id,
                    c.doc_id,
                    d.url,
                    d.title,
                    c.section_path,
                    c.position,
                    c.text,
                    ({score_expr}) AS score,
                    c.embedding
                FROM chunks AS c
                JOIN docs AS d ON d.doc_id = c.doc_id
                WHERE {where_expr}
                ORDER BY score DESC, c.position ASC
                LIMIT ?
            """
            rows = self.connection.execute(sql, like_params + like_params + [top]).fetchall()
        candidates = []
        for row in rows:
            (
                chunk_id,
                doc_id,
                url,
                title,
                section_path,
                position,
                text,
                score,
                embedding,
            ) = row
            candidates.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "url": url,
                    "title": title,
                    "section_path": section_path,
                    "position": position,
                    "text": text,
                    "score": float(score),
                    "embedding": list(embedding),
                }
            )
        if not candidates:
            logger.info("Búsqueda léxica sin resultados para query=%s", query)
        return candidates

    def dense_search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        cleaned = self._ensure_query(query)
        candidates = self._dense_candidates(cleaned, top_k=top_k)
        logger.info("Consulta densa '%s' → %d candidatos.", cleaned, len(candidates))
        return self._strip_internal(candidates)

    def lexical_search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        cleaned = self._ensure_query(query)
        candidates = self._lexical_candidates(cleaned, top_k=top_k)
        logger.info("Consulta léxica '%s' → %d candidatos.", cleaned, len(candidates))
        return self._strip_internal(candidates)

    def _apply_mmr(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        remaining = candidates[:]
        lambda_factor = self.config.mmr_lambda
        penalty = self.config.same_url_penalty

        while remaining and len(selected) < self.config.final_k:
            best_candidate = None
            best_score = float("-inf")
            for candidate in remaining:
                diversity = 0.0
                for chosen in selected:
                    similarity = _cosine_similarity(candidate.get("embedding"), chosen.get("embedding"))
                    if candidate.get("url") == chosen.get("url"):
                        similarity = max(similarity, 1.0 + penalty)
                    diversity = max(diversity, similarity)
                mmr_score = lambda_factor * candidate["score"] - (1 - lambda_factor) * diversity
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_candidate = candidate
            selected.append(best_candidate)
            remaining.remove(best_candidate)
        return selected

    def hybrid_search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        cleaned = self._ensure_query(query)
        dense_candidates = self._dense_candidates(cleaned, top_k=top_k or self.config.dense_topk)
        lexical_candidates = self._lexical_candidates(cleaned, top_k=top_k or self.config.lexical_topk)

        dense_norm = self._normalize(dense_candidates)
        lexical_norm = self._normalize(lexical_candidates)

        fused: Dict[str, Dict[str, Any]] = {}
        for origin, bucket in (("dense", dense_candidates), ("lexical", lexical_candidates)):
            norm_scores = dense_norm if origin == "dense" else lexical_norm
            for item in bucket:
                record = fused.setdefault(item["chunk_id"], deepcopy(item))
                key = f"{origin}_norm"
                record[key] = norm_scores.get(item["chunk_id"], 0.0)

        for record in fused.values():
            dense_score = record.get("dense_norm", 0.0)
            lexical_score = record.get("lexical_norm", 0.0)
            record["score"] = self.config.hybrid_alpha * dense_score + (1 - self.config.hybrid_alpha) * lexical_score

        candidate_pool = sorted(fused.values(), key=lambda x: x["score"], reverse=True)
        limit = max(self.config.final_k * 4, self.config.rerank_topk, 8)
        candidate_pool = candidate_pool[:limit]

        selected = self._apply_mmr(candidate_pool)

        if self.reranker and self.config.enable_rerank:
            selected = self.reranker.rerank(cleaned, selected, top_k=self.config.rerank_topk)

        final_norm = self._normalize(selected)
        for item in selected:
            item["score"] = final_norm.get(item["chunk_id"], item["score"])

        logger.info("Consulta híbrida '%s' → %d resultados finales.", cleaned, len(selected))
        return self._strip_internal(selected)

    def chunks_for_url(self, url: str) -> List[Dict[str, Any]]:
        cleaned = (url or "").strip()
        if not cleaned:
            logger.warning("Solicitud de chunks sin URL.")
            raise ValueError("Debes proporcionar una URL.")
        rows = self.connection.execute(
            """
            SELECT
                c.chunk_id,
                c.doc_id,
                d.url,
                d.title,
                c.section_path,
                c.position,
                c.text
            FROM chunks AS c
            JOIN docs AS d ON d.doc_id = c.doc_id
            WHERE d.url = ?
            ORDER BY c.position ASC
            """,
            [cleaned],
        ).fetchall()
        results = []
        for row in rows:
            chunk_id, doc_id, url, title, section_path, position, text = row
            results.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "url": url,
                    "title": title,
                    "section_path": section_path,
                    "position": position,
                    "text": text,
                    "score": 1.0,
                }
            )
        if not results:
            logger.warning("No se encontraron chunks para la URL: %s", cleaned)
            raise ValueError("No se encontraron chunks para la URL indicada.")
        logger.info("URL '%s' → %d chunks recuperados.", cleaned, len(results))
        return results


__all__ = ["Retriever"]
