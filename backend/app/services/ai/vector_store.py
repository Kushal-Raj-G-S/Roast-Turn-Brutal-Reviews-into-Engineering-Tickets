"""
Semantic memory for resolved issues — a real hybrid-search RAG stack:

  - Qdrant (embedded, on-disk, free — no server to run) stores dense
    embeddings + metadata for every analyzed cluster.
  - BM25 (rank_bm25) provides sparse/keyword search over the same corpus.
  - Dense + sparse rankings are fused with Reciprocal Rank Fusion (RRF).
  - A cross-encoder reranks the fused candidates against the live query for
    a final, much more precise ordering.

This is what lets the RCA agent answer "have we seen this before?" with
actual retrieved evidence instead of guessing from a single LLM call.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.bulk_embedding import EmbeddingBackend

logger = logging.getLogger(__name__)

_COLLECTION = "resolved_clusters"
_QDRANT_PATH = "./qdrant_data"
_VECTOR_DIM = 384  # matches all-MiniLM-L6-v2

_client: Optional[object] = None
_embedder: Optional[EmbeddingBackend] = None
_reranker: Optional[object] = None


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _get_client():
    """Lazily create the embedded (local, on-disk) Qdrant client."""
    global _client
    if _client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        logger.info(f"🔧 Opening embedded Qdrant store at {_QDRANT_PATH}")
        _client = QdrantClient(path=_QDRANT_PATH)
        existing = [c.name for c in _client.get_collections().collections]
        if _COLLECTION not in existing:
            _client.create_collection(
                collection_name=_COLLECTION,
                vectors_config=VectorParams(size=_VECTOR_DIM, distance=Distance.COSINE),
            )
            logger.info(f"✅ Created Qdrant collection '{_COLLECTION}'")
    return _client


def _get_embedder() -> EmbeddingBackend:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingBackend()
    return _embedder


def _get_reranker():
    """Lazily load a small, free cross-encoder for reranking."""
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        logger.info("🔧 Loading cross-encoder reranker (ms-marco-MiniLM-L-6-v2)")
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker


def index_cluster(cluster) -> None:
    """
    Add (or update) a cluster in the vector store once it has an RCA.
    Called right after a cluster's RCA is generated, so future uploads can
    retrieve it as precedent.
    """
    try:
        from qdrant_client.models import PointStruct

        client = _get_client()
        embedder = _get_embedder()

        text = f"{cluster.title} {' '.join(cluster.keywords or [])}"
        vector = embedder.encode_batch([text])[0].tolist()

        client.upsert(
            collection_name=_COLLECTION,
            points=[
                PointStruct(
                    id=cluster.id,
                    vector=vector,
                    payload={
                        "cluster_id": cluster.id,
                        "upload_id": cluster.upload_id,
                        "title": cluster.title,
                        "severity": cluster.severity,
                        "status": cluster.status,
                        "keywords": cluster.keywords or [],
                        "rca_hypothesis": cluster.rca_hypothesis,
                        "rca_fix": cluster.rca_fix,
                        "review_count": cluster.review_count,
                        "text": text,
                    },
                )
            ],
        )
        logger.info(f"✅ Indexed cluster {cluster.id} into vector store")
    except Exception as e:
        logger.warning(f"⚠️  Failed to index cluster {getattr(cluster, 'id', '?')}: {e}")


@dataclass
class SimilarIssue:
    cluster_id: int
    title: str
    severity: str
    status: str
    rca_hypothesis: Optional[str]
    rca_fix: Optional[str]
    score: float = 0.0


def _reciprocal_rank_fusion(
    dense_ids: list[int], sparse_ids: list[int], k: int = 60
) -> dict[int, float]:
    """Standard RRF: score = sum(1 / (k + rank)) across both rankings."""
    scores: dict[int, float] = {}
    for rank, doc_id in enumerate(dense_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    for rank, doc_id in enumerate(sparse_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


def hybrid_search(query: str, top_k: int = 5, exclude_cluster_id: Optional[int] = None) -> list[SimilarIssue]:
    """
    Dense (Qdrant/cosine) + sparse (BM25) retrieval, fused with RRF, then
    reranked with a cross-encoder against the raw query text.

    Returns [] gracefully if the store is empty or unavailable — this is a
    "have we seen this before" lookup, not a hard dependency.
    """
    try:
        from rank_bm25 import BM25Okapi

        client = _get_client()
        embedder = _get_embedder()

        count = client.count(collection_name=_COLLECTION).count
        if count == 0:
            return []

        # Pull the full corpus for BM25 (fine at this scale — a few thousand
        # resolved clusters at most; swap for a persistent BM25 index if this
        # ever needs to scale past that).
        all_points, _ = client.scroll(collection_name=_COLLECTION, limit=max(count, 1), with_payload=True, with_vectors=False)
        corpus_ids = [p.id for p in all_points]
        corpus_texts = [p.payload.get("text", "") for p in all_points]
        payloads = {p.id: p.payload for p in all_points}

        if exclude_cluster_id is not None:
            keep = [i for i, cid in enumerate(corpus_ids) if cid != exclude_cluster_id]
            corpus_ids = [corpus_ids[i] for i in keep]
            corpus_texts = [corpus_texts[i] for i in keep]

        if not corpus_ids:
            return []

        # Dense search
        query_vector = embedder.encode_batch([query])[0].tolist()
        dense_hits = client.query_points(
            collection_name=_COLLECTION,
            query=query_vector,
            limit=min(20, len(corpus_ids)),
        ).points
        dense_ids = [h.id for h in dense_hits if exclude_cluster_id is None or h.id != exclude_cluster_id]

        # Sparse (BM25) search over the same corpus
        bm25 = BM25Okapi([_tokenize(t) for t in corpus_texts])
        bm25_scores = bm25.get_scores(_tokenize(query))
        ranked_sparse = sorted(zip(corpus_ids, bm25_scores), key=lambda x: x[1], reverse=True)
        sparse_ids = [doc_id for doc_id, _ in ranked_sparse[:20]]

        fused = _reciprocal_rank_fusion(dense_ids, sparse_ids)
        candidate_ids = [doc_id for doc_id, _ in sorted(fused.items(), key=lambda x: x[1], reverse=True)][:10]

        if not candidate_ids:
            return []

        # Cross-encoder rerank of the fused candidates against the raw query
        reranker = _get_reranker()
        pairs = [(query, payloads[cid].get("text", "")) for cid in candidate_ids]
        rerank_scores = reranker.predict(pairs)
        reranked = sorted(zip(candidate_ids, rerank_scores), key=lambda x: x[1], reverse=True)[:top_k]

        return [
            SimilarIssue(
                cluster_id=cid,
                title=payloads[cid].get("title", ""),
                severity=payloads[cid].get("severity", ""),
                status=payloads[cid].get("status", ""),
                rca_hypothesis=payloads[cid].get("rca_hypothesis"),
                rca_fix=payloads[cid].get("rca_fix"),
                score=float(score),
            )
            for cid, score in reranked
        ]
    except Exception as e:
        logger.warning(f"⚠️  Hybrid search unavailable ({e}) — proceeding without precedent")
        return []
