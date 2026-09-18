"""
Golden-path regression tests for the review-processing pipeline.

Every assertion here pins a bug that actually shipped and was only caught by
running a real upload by hand -- exactly the class of failure a fast, offline
test should have caught first. All tests run without a database, without the
network, and without NVIDIA credentials (the embedding layer falls back to its
local TF-IDF tier), so they belong in the default `pytest` run, not the
`integration` marker.

The bugs pinned:
  1. Clustering collapse. The live clustering (bulk_processor._cluster_in_memory)
     once put ~96% of a 200k upload into ONE mega-cluster. It must produce
     balanced partitions, never a blob.
  2. Two clustering implementations. The frontend path uses
     app/services/bulk_processor.py (v1); the DDD pipeline + Airflow DAG use
     src/infrastructure/clustering/engines.py (v2). A fix applied to only one
     silently leaves the other broken (this happened). Both are tested here so
     they can't diverge unnoticed.
  3. NVIDIA embeddings never running. _nvidia_encode_batch called asyncio.run()
     from inside FastAPI's event loop, which always raises, so every upload
     silently degraded to TF-IDF. The async helper must work inside a loop.
"""

from collections import Counter

import numpy as np


def _blobs(n_clusters: int = 6, per: int = 160, dim: int = 64, seed: int = 0) -> np.ndarray:
    """Well-separated tight Gaussian blobs — the easy case any real clustering
    must handle. If an algorithm mega-blobs or shatters THIS, it is broken."""
    rng = np.random.default_rng(seed)
    centers = rng.normal(0.0, 10.0, size=(n_clusters, dim))
    pts = [c + rng.normal(0.0, 0.1, size=(per, dim)) for c in centers]
    return np.vstack(pts).astype("float32")


def _assert_balanced(labels, n):
    counts = Counter(labels)
    # Every point is assigned.
    assert len(labels) == n
    # No mega-blob: the original bug dumped ~96% into one cluster.
    assert max(counts.values()) < 0.5 * n, f"mega-blob: {max(counts.values())}/{n} in one cluster"
    # Not shattered into singletons.
    singletons = sum(1 for v in counts.values() if v == 1)
    assert singletons < 0.5 * len(counts), "clusters shattered into singletons"
    # k tracks ~n/150 (6 blobs of 160 -> ~6 clusters), allowing empty-cluster collapse.
    assert 4 <= len(counts) <= 7, f"unexpected cluster count {len(counts)}"


def test_live_clustering_is_balanced():
    """v1 (the path the frontend actually hits) must not mega-blob."""
    from app.services.bulk_processor import BulkProcessor

    bp = BulkProcessor.__new__(BulkProcessor)  # no DB needed for this pure method
    emb = _blobs()
    _assert_balanced(bp._cluster_in_memory(emb), len(emb))


async def test_engine_clustering_is_balanced():
    """v2 engine (DDD pipeline + Airflow DAG) must not mega-blob either."""
    from src.infrastructure.clustering.engines import FAISSClusteringEngine

    emb = _blobs()
    labels = await FAISSClusteringEngine().cluster(emb.tolist())
    _assert_balanced(labels, len(emb))


async def test_both_clustering_impls_stay_in_sync():
    """The two implementations must agree in shape, so a change to one that is
    not mirrored in the other is caught here rather than in production."""
    from app.services.bulk_processor import BulkProcessor
    from src.infrastructure.clustering.engines import FAISSClusteringEngine

    emb = _blobs()
    v1 = BulkProcessor.__new__(BulkProcessor)._cluster_in_memory(emb)
    v2 = await FAISSClusteringEngine().cluster(emb.tolist())
    # Same review-per-cluster target -> same K (allow ±1 for empty-cluster collapse).
    assert abs(len(set(v1)) - len(set(v2))) <= 1


def test_clustering_handles_tiny_inputs():
    """Edge cases that must never raise: empty, single, and below-K sizes."""
    from app.services.bulk_processor import BulkProcessor

    bp = BulkProcessor.__new__(BulkProcessor)
    assert bp._cluster_in_memory(np.zeros((0, 8), dtype="float32")) == []
    assert bp._cluster_in_memory(np.ones((1, 8), dtype="float32")) == [0]
    # 10 points, well under one 150-review cluster -> all one cluster, no crash.
    labels = bp._cluster_in_memory(_blobs(n_clusters=2, per=5))
    assert len(labels) == 10


async def test_nvidia_async_helper_runs_inside_event_loop():
    """Regression for the bug that silently disabled NVIDIA embeddings:
    _nvidia_encode_batch used asyncio.run(), which raises 'cannot be called
    from a running event loop' in the FastAPI request path. The helper must
    run a coroutine to completion even when a loop is already active (this
    test itself runs inside one)."""
    from app.services.bulk_embedding import _run_coro_blocking

    async def sample():
        return 42

    assert _run_coro_blocking(sample()) == 42


def test_async_helper_runs_without_a_loop():
    from app.services.bulk_embedding import _run_coro_blocking

    async def sample():
        return 7

    assert _run_coro_blocking(sample()) == 7
