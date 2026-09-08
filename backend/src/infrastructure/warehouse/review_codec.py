"""
Serialization codec for Review entities.

Exists because Review is a dataclass holding *nested* value objects
(ReviewMetadata, ActionabilityScore, EmbeddingVector), so neither
`review.__dict__` nor `Review(**d)` round-trips correctly — __dict__
leaves the nested objects as un-serializable instances, and Review(**d)
hands raw dicts back into fields typed as value objects. Every stage
handoff and warehouse load goes through this module instead.

Pure functions, no I/O — so the round-trip is unit-testable without GCS,
BigQuery or Kafka.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from ...domain.entities import Review
from ...domain.value_objects import (
    ActionabilityScore,
    ClusterId,
    EmbeddingVector,
    ReviewMetadata,
    TenantId,
)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(raw) if raw else None


def review_to_dict(review: Review) -> Dict[str, Any]:
    """Flatten a Review (and its nested value objects) into a JSON/Parquet-safe dict."""
    return {
        "id": review.id,
        "text": review.text,
        # ReviewMetadata
        "rating": review.metadata.rating if review.metadata else None,
        "version": review.metadata.version if review.metadata else None,
        "device": review.metadata.device if review.metadata else None,
        "review_date": _iso(review.metadata.review_date) if review.metadata else None,
        "is_verified": review.metadata.is_verified if review.metadata else False,
        # ActionabilityScore
        "actionability_score": review.actionability.score if review.actionability else None,
        "actionability_confidence": review.actionability.confidence if review.actionability else None,
        "actionability_features": review.actionability.features if review.actionability else None,
        "is_actionable": review.actionability.is_actionable if review.actionability else None,
        # EmbeddingVector
        "embedding": list(review.embedding.values) if review.embedding else None,
        "embedding_dimension": review.embedding.dimension if review.embedding else None,
        "embedding_model": review.embedding.model_name if review.embedding else None,
        # Identity
        "cluster_id": review.cluster_id.value if review.cluster_id else None,
        "tenant_id": str(review.tenant_id.value) if review.tenant_id else None,
        "created_at": _iso(review.created_at),
    }


def dict_to_review(d: Dict[str, Any]) -> Review:
    """Rebuild a Review, reconstructing each nested value object properly."""
    metadata = ReviewMetadata(
        rating=d.get("rating"),
        version=d.get("version"),
        device=d.get("device"),
        review_date=_parse_dt(d.get("review_date")),
        is_verified=bool(d.get("is_verified", False)),
    )

    actionability = None
    if d.get("actionability_score") is not None:
        actionability = ActionabilityScore(
            score=d["actionability_score"],
            confidence=d.get("actionability_confidence", 0.0),
            features=d.get("actionability_features") or {},
            is_actionable=bool(d.get("is_actionable", False)),
        )

    embedding = None
    if d.get("embedding") is not None:
        values = list(d["embedding"])
        embedding = EmbeddingVector(
            values=values,
            dimension=d.get("embedding_dimension") or len(values),
            model_name=d.get("embedding_model") or "unknown",
        )

    return Review(
        id=d.get("id"),
        text=d["text"],
        metadata=metadata,
        actionability=actionability,
        embedding=embedding,
        cluster_id=ClusterId(d["cluster_id"]) if d.get("cluster_id") else None,
        tenant_id=TenantId(UUID(d["tenant_id"])) if d.get("tenant_id") else None,
        created_at=_parse_dt(d.get("created_at")) or datetime.utcnow(),
    )


def reviews_to_records(reviews: List[Review]) -> List[Dict[str, Any]]:
    return [review_to_dict(r) for r in reviews]


def records_to_reviews(records: List[Dict[str, Any]]) -> List[Review]:
    return [dict_to_review(r) for r in records]
