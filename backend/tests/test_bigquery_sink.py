"""
Schema/config tests for BigQueryWarehouseSink — no network, no GCP
credentials required.
"""

from src.domain.entities import Review
from src.domain.value_objects import ReviewMetadata
from src.infrastructure.warehouse.bigquery_sink import (
    CLUSTERS_SCHEMA,
    REVIEW_EXCLUDED_COLUMNS,
    REVIEWS_SCHEMA,
    UPLOAD_METRICS_SCHEMA,
    BigQueryWarehouseSink,
)
from src.infrastructure.warehouse.review_codec import review_to_dict


def test_schemas_use_valid_bigquery_types():
    valid = {"STRING", "INTEGER", "FLOAT", "BOOLEAN", "TIMESTAMP"}
    for schema in (REVIEWS_SCHEMA, CLUSTERS_SCHEMA, UPLOAD_METRICS_SCHEMA):
        for name, dtype in schema:
            assert dtype in valid, f"{name} has unexpected type {dtype}"


def test_reviews_schema_has_partition_and_cluster_keys():
    names = {n for n, _ in REVIEWS_SCHEMA}
    assert "ingested_at" in names   # partition field
    assert "tenant_id" in names     # clustering field
    assert "upload_id" in names     # clustering field + idempotent delete key


def test_clusters_schema_carries_issue_fingerprint():
    """Without this column the regression model has no stable join key."""
    names = {n for n, _ in CLUSTERS_SCHEMA}
    assert "issue_fingerprint" in names
    assert "tenant_id" in names


def test_upload_metrics_schema_supports_shadow_deployment_versions():
    names = {n for n, _ in UPLOAD_METRICS_SCHEMA}
    assert "pipeline_version" in names


def test_raw_embedding_is_not_stored_in_warehouse():
    """
    Vectors belong in Qdrant. Persisting 200K x 384 floats into an
    analytical table inflates bytes-billed for every query that never
    touches them.
    """
    names = {n for n, _ in REVIEWS_SCHEMA}
    assert "embedding" not in names
    assert "embedding_dimension" in names  # lineage retained
    assert "embedding_model" in names
    assert "embedding" in REVIEW_EXCLUDED_COLUMNS


def test_excluded_columns_actually_appear_in_codec_output():
    """
    Guards against the exclusion list going stale: every column we claim to
    drop must actually be produced by the codec, or the filter is a no-op
    hiding a real schema mismatch.
    """
    record = review_to_dict(Review(id=1, text="x", metadata=ReviewMetadata()))
    for column in REVIEW_EXCLUDED_COLUMNS:
        assert column in record, f"{column} is excluded but codec never emits it"


def test_sink_construction_makes_no_network_call():
    sink = BigQueryWarehouseSink(project_id="test-project")
    assert sink.dataset == "roast_warehouse"
    assert sink._client is None  # lazy init


def test_table_id_is_fully_qualified():
    sink = BigQueryWarehouseSink(project_id="proj", dataset="ds")
    assert sink._table_id("reviews") == "proj.ds.reviews"


def test_invalid_identifiers_are_rejected():
    """
    BigQuery can't parameterize table identifiers, so the DELETE statements
    interpolate them. Construction-time validation is what makes that safe.
    """
    import pytest

    for bad in ["proj; DROP TABLE x", "proj`", "has space", "", r"back\slash"]:
        with pytest.raises(ValueError):
            BigQueryWarehouseSink(project_id=bad)

    with pytest.raises(ValueError):
        BigQueryWarehouseSink(project_id="ok-proj", dataset="bad;name")


def test_valid_identifiers_are_accepted():
    # Real GCP project ids contain dashes; datasets use underscores.
    sink = BigQueryWarehouseSink(project_id="my-gcp-project-123", dataset="roast_warehouse")
    assert sink.project_id == "my-gcp-project-123"
