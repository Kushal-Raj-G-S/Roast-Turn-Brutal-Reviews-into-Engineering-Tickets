"""
Round-trip tests for the Review codec.

These exist because the naive approach (review.__dict__ / Review(**d))
silently produces broken Review objects: the nested ReviewMetadata,
ActionabilityScore and EmbeddingVector value objects come back as plain
dicts, and downstream code that does review.metadata.rating then fails
with an AttributeError deep inside a pipeline stage. These tests pin the
round-trip so that can't regress.
"""

from datetime import datetime
from uuid import uuid4

import pytest

from src.domain.entities import Review
from src.domain.value_objects import (
    ActionabilityScore,
    ClusterId,
    EmbeddingVector,
    ReviewMetadata,
    TenantId,
)
from src.infrastructure.warehouse.review_codec import (
    dict_to_review,
    records_to_reviews,
    review_to_dict,
    reviews_to_records,
)


def _full_review() -> Review:
    return Review(
        id=42,
        text="App crashes on startup after the update",
        metadata=ReviewMetadata(
            rating=1,
            version="3.2.1",
            device="Pixel 7",
            review_date=datetime(2026, 3, 14, 10, 30),
            is_verified=True,
        ),
        actionability=ActionabilityScore(
            score=0.87,
            confidence=0.92,
            features={"has_negative_keyword": 1.0, "length": 38},
            is_actionable=True,
        ),
        embedding=EmbeddingVector(
            values=[0.1, -0.2, 0.3, 0.4],
            dimension=4,
            model_name="paraphrase-MiniLM-L3-v2",
        ),
        cluster_id=ClusterId(str(uuid4())),
        tenant_id=TenantId(uuid4()),
        created_at=datetime(2026, 3, 14, 11, 0),
    )


def test_round_trip_preserves_nested_value_objects():
    original = _full_review()
    restored = dict_to_review(review_to_dict(original))

    # The whole point: these must be value objects, not dicts.
    assert isinstance(restored.metadata, ReviewMetadata)
    assert isinstance(restored.actionability, ActionabilityScore)
    assert isinstance(restored.embedding, EmbeddingVector)
    assert isinstance(restored.cluster_id, ClusterId)
    assert isinstance(restored.tenant_id, TenantId)


def test_round_trip_preserves_values():
    original = _full_review()
    restored = dict_to_review(review_to_dict(original))

    assert restored.id == original.id
    assert restored.text == original.text
    assert restored.metadata.rating == 1
    assert restored.metadata.version == "3.2.1"
    assert restored.metadata.device == "Pixel 7"
    assert restored.metadata.review_date == original.metadata.review_date
    assert restored.metadata.is_verified is True
    assert restored.actionability.score == pytest.approx(0.87)
    assert restored.actionability.is_actionable is True
    assert restored.embedding.values == pytest.approx(original.embedding.values)
    assert restored.embedding.dimension == 4
    assert restored.embedding.model_name == "paraphrase-MiniLM-L3-v2"
    assert restored.cluster_id.value == original.cluster_id.value
    assert restored.tenant_id.value == original.tenant_id.value


def test_round_trip_handles_minimal_review():
    """A review straight out of CSV loading has no score/embedding/cluster yet."""
    minimal = Review(
        id=None,
        text="ok",
        metadata=ReviewMetadata(),
    )
    restored = dict_to_review(review_to_dict(minimal))

    assert restored.text == "ok"
    assert restored.actionability is None
    assert restored.embedding is None
    assert restored.cluster_id is None
    assert restored.tenant_id is None
    assert restored.metadata.rating is None


def test_batch_round_trip():
    reviews = [_full_review() for _ in range(5)]
    restored = records_to_reviews(reviews_to_records(reviews))

    assert len(restored) == 5
    assert all(isinstance(r.embedding, EmbeddingVector) for r in restored)


def test_records_are_json_serializable():
    """Parquet/BigQuery loads require primitives, not value objects."""
    import json

    record = review_to_dict(_full_review())
    json.dumps(record)  # raises TypeError if any value object leaked through
