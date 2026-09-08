"""
Integration test for the regression-detection SQL logic, run against a
real BigQuery-dialect engine (the BigQuery emulator).

Why this test exists: the first version of regression_detection.sql
partitioned LAG() by cluster_id. cluster_id is a fresh UUID per upload, so
the same issue never matched across pipeline versions and the model would
have reported zero regressions forever while looking perfectly healthy.
That is exactly the class of bug unit tests cannot catch — the SQL was
valid, the dbt build was green, and the answer was silently always empty.

These tests execute both the broken and the fixed windowing against real
data and assert the difference, so the claim in
docs/PLATFORM_REARCHITECTURE.md is demonstrated rather than asserted.

Run with:

    docker run -d --name roast-bq-test -p 9050:9050 \
      ghcr.io/goccy/bigquery-emulator:latest \
      --project=test-project --dataset=roast_warehouse

    pytest tests/integration/test_regression_sql_integration.py -v
"""

import os
import socket
import uuid

import pytest

pytestmark = pytest.mark.integration

BQ_ENDPOINT = os.getenv("BIGQUERY_EMULATOR_HOST", "localhost:9050")
PROJECT = "test-project"
DATASET = "roast_warehouse"


def _reachable() -> bool:
    host, _, port = BQ_ENDPOINT.partition(":")
    try:
        with socket.create_connection((host, int(port or 9050)), timeout=3):
            return True
    except OSError:
        return False


pytest.importorskip("google.cloud.bigquery", reason="google-cloud-bigquery not installed")

if not _reachable():
    pytest.skip(f"No BigQuery emulator at {BQ_ENDPOINT}", allow_module_level=True)

from src.infrastructure.warehouse.bigquery_sink import (  # noqa: E402
    compute_issue_fingerprint,
)


@pytest.fixture(scope="module")
def client():
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import bigquery

    return bigquery.Client(
        project=PROJECT,
        credentials=AnonymousCredentials(),
        client_options={"api_endpoint": f"http://{BQ_ENDPOINT}"},
    )


def _query(client, sql: str):
    return list(client.query(sql).result())


# Three pipeline runs of the SAME underlying issue. Note each run assigns a
# DIFFERENT cluster_id (a fresh UUID), which is precisely the real-world
# behaviour that broke the original model.
TENANT = "11111111-1111-1111-1111-111111111111"
ISSUE_TITLE = "App crashes on startup"
ISSUE_KEYWORDS = ["crash", "startup"]
FINGERPRINT = compute_issue_fingerprint(ISSUE_TITLE, ISSUE_KEYWORDS)

RUNS = [
    # (pipeline_version, severity, review_count)
    ("v1", "medium", 100),
    ("v2", "high", 140),      # severity worsened  -> REGRESSED_SEVERITY
    ("v3", "high", 260),      # volume surged >50% -> REGRESSED_VOLUME
]


@pytest.fixture(scope="module")
def seeded(client):
    """Create a clusters-like table with one row per pipeline run."""
    table = f"{PROJECT}.{DATASET}.regr_fixture_{uuid.uuid4().hex[:8]}"

    client.query(f"""
        CREATE TABLE `{table}` (
            tenant_id STRING,
            cluster_id STRING,
            issue_fingerprint STRING,
            title STRING,
            severity STRING,
            review_count INT64,
            pipeline_version STRING,
            run_seq INT64
        )
    """).result()

    values = ",\n".join(
        f"('{TENANT}', '{uuid.uuid4()}', '{FINGERPRINT}', '{ISSUE_TITLE}', "
        f"'{sev}', {cnt}, '{ver}', {i})"
        for i, (ver, sev, cnt) in enumerate(RUNS)
    )
    client.query(f"INSERT INTO `{table}` VALUES\n{values}").result()
    return table


def test_every_run_has_a_distinct_cluster_id(client, seeded):
    """Confirms the premise: cluster_id is NOT stable across runs."""
    rows = _query(client, f"SELECT COUNT(DISTINCT cluster_id) AS n FROM `{seeded}`")
    assert rows[0].n == 3, "fixture should have a unique cluster_id per run"

    rows = _query(client, f"SELECT COUNT(DISTINCT issue_fingerprint) AS n FROM `{seeded}`")
    assert rows[0].n == 1, "fingerprint should be identical across runs"


def test_partitioning_by_cluster_id_finds_nothing(client, seeded):
    """
    The ORIGINAL (broken) logic. Every LAG() is NULL because each row is
    alone in its partition, so every row classifies as 'NEW' and no
    regression is ever reported. This is the bug, demonstrated.
    """
    rows = _query(client, f"""
        WITH with_lag AS (
            SELECT
                pipeline_version,
                severity,
                review_count,
                LAG(severity) OVER (
                    PARTITION BY tenant_id, cluster_id ORDER BY run_seq
                ) AS prev_severity,
                LAG(review_count) OVER (
                    PARTITION BY tenant_id, cluster_id ORDER BY run_seq
                ) AS prev_review_count
            FROM `{seeded}`
        )
        SELECT
            COUNTIF(prev_severity IS NULL) AS null_lags,
            COUNT(*) AS total
        FROM with_lag
    """)
    assert rows[0].null_lags == rows[0].total == 3, (
        "cluster_id partitioning must produce all-NULL lags — that's the bug"
    )


def test_partitioning_by_fingerprint_detects_regressions(client, seeded):
    """
    The FIXED logic: partitioning by issue_fingerprint chains the runs
    together, so LAG() sees the previous version and the severity/volume
    comparisons actually fire.
    """
    rows = _query(client, f"""
        WITH severity_rank AS (
            SELECT 'low' AS severity, 1 AS rank UNION ALL
            SELECT 'medium', 2 UNION ALL
            SELECT 'high', 3 UNION ALL
            SELECT 'critical', 4
        ),
        runs AS (
            SELECT c.*, COALESCE(sr.rank, 0) AS severity_rank
            FROM `{seeded}` c
            LEFT JOIN severity_rank sr ON sr.severity = c.severity
        ),
        with_lag AS (
            SELECT
                pipeline_version,
                severity,
                review_count,
                severity_rank,
                LAG(severity) OVER w AS prev_severity,
                LAG(severity_rank) OVER w AS prev_severity_rank,
                LAG(review_count) OVER w AS prev_review_count,
                LAG(pipeline_version) OVER w AS prev_pipeline_version
            FROM runs
            WINDOW w AS (
                PARTITION BY tenant_id, issue_fingerprint ORDER BY run_seq
            )
        )
        SELECT
            pipeline_version,
            prev_pipeline_version,
            prev_severity,
            severity,
            prev_review_count,
            review_count,
            CASE
                WHEN prev_pipeline_version IS NULL THEN 'NEW'
                WHEN severity_rank > prev_severity_rank THEN 'REGRESSED_SEVERITY'
                WHEN review_count > prev_review_count * 1.5 THEN 'REGRESSED_VOLUME'
                WHEN severity_rank < prev_severity_rank
                  OR review_count < prev_review_count * 0.5 THEN 'IMPROVED'
                ELSE 'STABLE'
            END AS regression_status
        FROM with_lag
        ORDER BY pipeline_version
    """)

    statuses = {r.pipeline_version: r.regression_status for r in rows}

    assert statuses["v1"] == "NEW", statuses
    # v2: medium -> high
    assert statuses["v2"] == "REGRESSED_SEVERITY", statuses
    # v3: severity flat, but 140 -> 260 is >1.5x
    assert statuses["v3"] == "REGRESSED_VOLUME", statuses

    # The lag actually chained runs together.
    by_version = {r.pipeline_version: r for r in rows}
    assert by_version["v2"].prev_pipeline_version == "v1"
    assert by_version["v3"].prev_pipeline_version == "v2"
    assert by_version["v2"].prev_review_count == 100
    assert by_version["v3"].prev_review_count == 140


def test_improvement_is_distinguished_from_regression(client):
    """A genuinely fixed issue must classify as IMPROVED, not flagged."""
    table = f"{PROJECT}.{DATASET}.improve_fixture_{uuid.uuid4().hex[:8]}"
    fp = compute_issue_fingerprint("Login fails", ["login"])

    client.query(f"""
        CREATE TABLE `{table}` (
            tenant_id STRING, issue_fingerprint STRING,
            severity STRING, review_count INT64,
            pipeline_version STRING, run_seq INT64
        )
    """).result()
    client.query(f"""
        INSERT INTO `{table}` VALUES
          ('{TENANT}', '{fp}', 'critical', 400, 'v1', 0),
          ('{TENANT}', '{fp}', 'low', 20, 'v2', 1)
    """).result()

    rows = _query(client, f"""
        WITH severity_rank AS (
            SELECT 'low' AS severity, 1 AS rank UNION ALL
            SELECT 'medium', 2 UNION ALL
            SELECT 'high', 3 UNION ALL
            SELECT 'critical', 4
        ),
        runs AS (
            SELECT c.*, COALESCE(sr.rank, 0) AS severity_rank
            FROM `{table}` c
            LEFT JOIN severity_rank sr ON sr.severity = c.severity
        ),
        with_lag AS (
            SELECT
                pipeline_version, severity_rank, review_count,
                LAG(severity_rank) OVER w AS prev_severity_rank,
                LAG(review_count) OVER w AS prev_review_count,
                LAG(pipeline_version) OVER w AS prev_pipeline_version
            FROM runs
            WINDOW w AS (PARTITION BY tenant_id, issue_fingerprint ORDER BY run_seq)
        )
        SELECT pipeline_version,
            CASE
                WHEN prev_pipeline_version IS NULL THEN 'NEW'
                WHEN severity_rank > prev_severity_rank THEN 'REGRESSED_SEVERITY'
                WHEN review_count > prev_review_count * 1.5 THEN 'REGRESSED_VOLUME'
                WHEN severity_rank < prev_severity_rank
                  OR review_count < prev_review_count * 0.5 THEN 'IMPROVED'
                ELSE 'STABLE'
            END AS regression_status
        FROM with_lag ORDER BY pipeline_version
    """)
    statuses = {r.pipeline_version: r.regression_status for r in rows}
    assert statuses["v2"] == "IMPROVED", statuses
