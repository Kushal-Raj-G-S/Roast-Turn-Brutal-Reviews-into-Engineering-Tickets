"""
Integration tests for GCSStagingStore against a REAL GCS-compatible server.

This is the piece the whole DAG depends on — if the Parquet round-trip
through object storage loses or corrupts a field, every downstream stage
silently gets bad data. The unit tests cover the codec in memory; these
cover the actual upload/download path, including the 384-dimension
embedding vectors that motivated staging in the first place.

Run with:

    docker run -d --name roast-gcs-test -p 4443:4443 \
      fsouza/fake-gcs-server:latest \
      -scheme http -port 4443 -external-url http://localhost:4443 -backend memory

    pytest tests/integration/ -v

Skipped automatically when no server is reachable.
"""

import contextlib
import os
import socket
import uuid
from datetime import datetime

import pytest

pytestmark = pytest.mark.integration

GCS_ENDPOINT = os.getenv("GCS_EMULATOR_HOST", "localhost:4443")
BUCKET = "roast-staging-test"


def _reachable() -> bool:
    host, _, port = GCS_ENDPOINT.partition(":")
    try:
        with socket.create_connection((host, int(port or 4443)), timeout=3):
            return True
    except OSError:
        return False


pytest.importorskip("google.cloud.storage", reason="google-cloud-storage not installed")
pytest.importorskip("pyarrow", reason="pyarrow not installed")

if not _reachable():
    pytest.skip(f"No GCS emulator at {GCS_ENDPOINT}", allow_module_level=True)

# The client library reads these at construction; must be set before import-time use.
os.environ["STORAGE_EMULATOR_HOST"] = f"http://{GCS_ENDPOINT}"

from src.domain.entities import Review  # noqa: E402
from src.domain.value_objects import (  # noqa: E402
    ActionabilityScore,
    ClusterId,
    EmbeddingVector,
    ReviewMetadata,
    TenantId,
)
from src.infrastructure.warehouse.gcs_staging import GCSStagingStore  # noqa: E402


@pytest.fixture(scope="module")
def bucket_ready():
    """Create the test bucket in the emulator once."""
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import storage

    client = storage.Client(
        project="test-project", credentials=AnonymousCredentials()
    )
    with contextlib.suppress(Exception):
        client.create_bucket(BUCKET)  # already exists
    return client


@pytest.fixture
def store(bucket_ready):
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import storage

    s = GCSStagingStore(bucket=BUCKET, project_id="test-project")
    # Inject an anonymous-credential client — the emulator has no auth.
    s._client = storage.Client(
        project="test-project", credentials=AnonymousCredentials()
    )
    return s


def _review(i: int, dim: int = 384) -> Review:
    return Review(
        id=i,
        text=f"App crashes on startup, review {i}",
        metadata=ReviewMetadata(
            rating=1,
            version="3.2.1",
            device="Pixel 7",
            review_date=datetime(2026, 3, 14, 10, 30),
            is_verified=True,
        ),
        actionability=ActionabilityScore(
            score=0.87, confidence=0.92,
            features={"has_negative_keyword": 1.0}, is_actionable=True,
        ),
        embedding=EmbeddingVector(
            values=[i * 0.001 + j * 0.0001 for j in range(dim)],
            dimension=dim,
            model_name="paraphrase-MiniLM-L3-v2",
        ),
        cluster_id=ClusterId(str(uuid.uuid4())),
        tenant_id=TenantId(uuid.uuid4()),
        created_at=datetime(2026, 3, 14, 11, 0),
    )


def test_write_then_read_preserves_everything(store):
    """The core claim: a stage handoff through GCS loses nothing."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    originals = [_review(i) for i in range(50)]

    uri = store.write_reviews(originals, upload_id=999, run_id=run_id, stage="embedding")
    assert uri.startswith(f"gs://{BUCKET}/")

    restored = store.read_reviews(uri)
    assert len(restored) == 50

    for orig, got in zip(originals, restored, strict=True):
        assert got.id == orig.id
        assert got.text == orig.text
        assert got.metadata.rating == orig.metadata.rating
        assert got.metadata.device == orig.metadata.device
        assert got.metadata.review_date == orig.metadata.review_date
        assert got.actionability.is_actionable is True
        assert got.embedding.dimension == 384
        assert len(got.embedding.values) == 384
        # Float fidelity through Parquet — the thing most likely to drift.
        assert got.embedding.values == pytest.approx(orig.embedding.values)
        assert got.cluster_id.value == orig.cluster_id.value
        assert got.tenant_id.value == orig.tenant_id.value


def test_run_scoped_paths_do_not_collide(store):
    """
    A backfill re-run must not overwrite the original run's artifacts —
    that's what makes post-mortem inspection of a failed run possible.
    """
    run_a, run_b = "run-aaa", "run-bbb"

    uri_a = store.write_reviews([_review(1)], upload_id=42, run_id=run_a, stage="embedding")
    uri_b = store.write_reviews([_review(2)], upload_id=42, run_id=run_b, stage="embedding")

    assert uri_a != uri_b
    assert store.read_reviews(uri_a)[0].id == 1
    assert store.read_reviews(uri_b)[0].id == 2  # A was not clobbered


def test_stages_within_a_run_are_separate_objects(store):
    """Each stage's output is its own artifact, so a failed stage can be
    re-run from the previous stage's output."""
    run_id = f"run-{uuid.uuid4().hex[:8]}"

    filtered_uri = store.write_reviews(
        [_review(i) for i in range(3)], upload_id=7, run_id=run_id, stage="filter_noise"
    )
    embedded_uri = store.write_reviews(
        [_review(i) for i in range(2)], upload_id=7, run_id=run_id, stage="generate_embeddings"
    )

    assert filtered_uri != embedded_uri
    assert len(store.read_reviews(filtered_uri)) == 3
    assert len(store.read_reviews(embedded_uri)) == 2


def test_cleanup_removes_only_that_run(store):
    """Cleanup on success must not touch a different run's artifacts."""
    keep_run = f"keep-{uuid.uuid4().hex[:8]}"
    drop_run = f"drop-{uuid.uuid4().hex[:8]}"

    keep_uri = store.write_reviews([_review(1)], upload_id=55, run_id=keep_run, stage="embedding")
    store.write_reviews([_review(2)], upload_id=55, run_id=drop_run, stage="embedding")

    deleted = store.cleanup_run(upload_id=55, run_id=drop_run)
    assert deleted >= 1

    # The other run survives.
    assert store.read_reviews(keep_uri)[0].id == 1


def test_empty_review_list_round_trips(store):
    """
    Aggressive noise filtering can legitimately empty a batch. That must
    not blow up the stage handoff.
    """
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    uri = store.write_reviews([], upload_id=1, run_id=run_id, stage="filter_noise")
    assert store.read_reviews(uri) == []


def test_parquet_is_smaller_than_json_equivalent(store):
    """
    Documents the reason staging exists: this payload cannot fit through
    Airflow XCom (48KB limit on the default backend), and Parquet is far
    cheaper than JSON for embedding vectors.
    """
    import json

    from src.infrastructure.warehouse.review_codec import reviews_to_records

    reviews = [_review(i) for i in range(100)]
    json_bytes = len(json.dumps(reviews_to_records(reviews)))

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    uri = store.write_reviews(reviews, upload_id=1, run_id=run_id, stage="embedding")

    blob_path = uri.replace(f"gs://{BUCKET}/", "")
    # get_blob() fetches metadata; blob() alone returns an unpopulated
    # reference whose .size is None.
    parquet_bytes = store._client.bucket(BUCKET).get_blob(blob_path).size

    assert json_bytes > 48 * 1024, "sample should exceed the XCom limit to be meaningful"
    assert parquet_bytes < json_bytes
    print(
        f"\n100 reviews x 384-dim: JSON {json_bytes/1024:.0f}KB "
        f"vs Parquet {parquet_bytes/1024:.0f}KB "
        f"({json_bytes/parquet_bytes:.1f}x smaller); XCom limit is 48KB"
    )
