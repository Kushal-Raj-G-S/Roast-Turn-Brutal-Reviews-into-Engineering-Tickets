"""
BigQuery warehouse sink.

Why this exists alongside Postgres (not instead of it):
    Postgres (via PostgresUploadRepository / PostgresClusterRepository)
    stays the OLTP store — single-upload reads/writes, the live dashboard,
    row-level status updates. That's what Postgres is good at.

    BigQuery is the OLAP sink: analytical scans across every upload a
    tenant has ever made (cluster trend-lines, cross-upload regression
    detection, "how has this issue moved across v1/v2/v3"). Those are
    full-table columnar scans over hundreds of thousands of rows — the
    query shape Postgres row-storage is the wrong engine for. dbt (see
    /dbt/roast_dbt) builds its staging/mart models on the tables written
    here.

Load strategy — batch load jobs, NOT streaming inserts:
    insert_rows_json() (the streaming API) is billed per GB, quota-limited,
    caps requests at ~10MB, and rows sit in a streaming buffer where
    they're not immediately partition-pruneable. For 200K-row batches the
    correct API is a *load job* — free, atomic per-job, and it reads the
    Parquet that GCSStagingStore already wrote, so there's no second
    serialization pass.

    Streaming is kept only for the tiny per-run upload_metrics row, where
    low latency matters and volume is one row.

Requires: pip install google-cloud-bigquery
"""

import hashlib
import logging
import os
import re
from datetime import datetime
from typing import List, Optional

from ...domain.entities import Cluster, Review, Upload
from ...domain.value_objects import ProcessingMetrics
from .review_codec import reviews_to_records

logger = logging.getLogger(__name__)

DATASET = "roast_warehouse"

# Explicit schemas. Declared (rather than autodetected) so a malformed
# upstream payload fails the load job loudly instead of silently creating
# a drifted column.
REVIEWS_SCHEMA = [
    ("id", "INTEGER"),
    ("text", "STRING"),
    ("rating", "INTEGER"),
    ("version", "STRING"),
    ("device", "STRING"),
    ("review_date", "TIMESTAMP"),
    ("is_verified", "BOOLEAN"),
    ("actionability_score", "FLOAT"),
    ("actionability_confidence", "FLOAT"),
    ("is_actionable", "BOOLEAN"),
    ("embedding_dimension", "INTEGER"),
    ("embedding_model", "STRING"),
    ("cluster_id", "STRING"),
    ("tenant_id", "STRING"),
    ("created_at", "TIMESTAMP"),
    ("upload_id", "INTEGER"),
    ("ingested_at", "TIMESTAMP"),
]

CLUSTERS_SCHEMA = [
    ("cluster_id", "STRING"),
    ("upload_id", "INTEGER"),
    ("tenant_id", "STRING"),
    ("title", "STRING"),
    ("issue_fingerprint", "STRING"),  # stable cross-version identity — see below
    ("severity", "STRING"),
    ("status", "STRING"),
    ("review_count", "INTEGER"),
    ("avg_rating", "FLOAT"),
    ("affected_versions", "STRING"),
    ("keywords", "STRING"),
    ("ai_analyzed", "BOOLEAN"),
    ("created_at", "TIMESTAMP"),
    ("ingested_at", "TIMESTAMP"),
]

UPLOAD_METRICS_SCHEMA = [
    ("upload_id", "INTEGER"),
    ("tenant_id", "STRING"),
    ("total_reviews", "INTEGER"),
    ("filtered_noise", "INTEGER"),
    ("actionable_reviews", "INTEGER"),
    ("clusters_created", "INTEGER"),
    ("processing_time_ms", "INTEGER"),
    ("pipeline_version", "STRING"),
    ("created_at", "TIMESTAMP"),
]

# Columns excluded from the warehouse load. The raw 384-float embedding is
# deliberately NOT stored in BigQuery: Qdrant is the vector store and
# owns similarity search, and persisting 200K x 384 floats into an
# analytical table inflates every scan's bytes-billed for queries that
# never use the vector. Dimension/model are kept for lineage.
REVIEW_EXCLUDED_COLUMNS = ["embedding", "actionability_features"]

# BigQuery identifiers: letters, digits, underscores, dashes (project ids)
# and dots are the only legal characters. Anything else cannot be a valid
# identifier, so rejecting it closes the interpolation hole entirely.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _validate_identifier(value: str, kind: str) -> str:
    """
    Guard for identifiers interpolated into SQL. BigQuery does not support
    query parameters for table/dataset names, so DELETE statements must
    build them by string interpolation; every *value* in those statements
    is bound via ScalarQueryParameter instead.
    """
    if not value or not _IDENTIFIER_RE.match(value):
        raise ValueError(
            f"Invalid BigQuery {kind}: {value!r}. "
            "Only letters, digits, underscores and dashes are permitted."
        )
    return value


def compute_issue_fingerprint(title: str, keywords: Optional[List[str]] = None) -> str:
    """
    Stable identity for "the same issue" across pipeline runs.

    cluster_id is a fresh UUID per upload, so it CANNOT be used to track an
    issue across v1/v2/v3 shadow deployments — LAG() partitioned by
    cluster_id would never match anything. The regression-detection model
    partitions by this fingerprint instead: a normalized, order-independent
    hash of the cluster's title tokens plus its top keywords, so the same
    underlying issue hashes identically across runs even when its UUID and
    review count change.
    """
    tokens = set(re.findall(r"[a-z0-9]+", (title or "").lower()))
    # Drop very common filler so a re-worded title still matches
    tokens -= {"the", "a", "an", "is", "are", "app", "issue", "problem", "with", "and", "of", "to"}
    if keywords:
        tokens |= {k.strip().lower() for k in keywords if k and k.strip()}

    canonical = "|".join(sorted(tokens))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


class BigQueryWarehouseSink:
    """
    Loads pipeline output into BigQuery, partitioned by ingestion date and
    clustered by tenant — so the daily DAG task and dashboard queries scan
    one partition rather than the whole table. BigQuery bills by bytes
    scanned, so this is a cost decision, not a schema nicety.
    """

    def __init__(self, project_id: str, dataset: str = DATASET, location: str = "US"):
        # Validated at construction, not at query time. BigQuery has no
        # parameter binding for table identifiers, so every DELETE below
        # must interpolate them — validating here is what makes that
        # interpolation provably safe rather than merely conventional.
        self.project_id = _validate_identifier(project_id, "project_id")
        self.dataset = _validate_identifier(dataset, "dataset")
        self.location = location
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google.cloud import bigquery

            # BIGQUERY_EMULATOR_HOST is unset in every real deployment, so
            # this changes nothing about the ADC-authenticated path against
            # real GCP. It exists because the client has no built-in
            # emulator awareness (unlike google-cloud-storage's
            # STORAGE_EMULATOR_HOST) — without this, the only way to point
            # this class at a local/CI emulator was to not use this class
            # at all, which is exactly what happened: every prior emulator
            # test built its own throwaway bigquery.Client and never
            # exercised this sink.
            emulator_host = os.getenv("BIGQUERY_EMULATOR_HOST")
            if emulator_host:
                from google.auth.credentials import AnonymousCredentials

                self._client = bigquery.Client(
                    project=self.project_id,
                    credentials=AnonymousCredentials(),
                    client_options={"api_endpoint": f"http://{emulator_host}"},
                )
            else:
                self._client = bigquery.Client(project=self.project_id)
        return self._client

    def _table_id(self, table: str) -> str:
        """
        Fully-qualified table id. `table` is validated even though every
        current caller passes a literal — an unvalidated path here is
        exactly how a future caller introduces an injection.
        """
        return f"{self.project_id}.{self.dataset}.{_validate_identifier(table, 'table')}"

    def ensure_schema(self) -> None:
        """Idempotent: create dataset + partitioned/clustered tables if absent."""
        from google.cloud import bigquery

        client = self._get_client()
        dataset_ref = bigquery.DatasetReference(self.project_id, self.dataset)

        try:
            client.get_dataset(dataset_ref)
        except Exception:
            ds = bigquery.Dataset(dataset_ref)
            ds.location = self.location
            client.create_dataset(ds, exists_ok=True)
            logger.info(f"Created BigQuery dataset {self.dataset}")

        for table_name, schema_fields, partition_field, cluster_by in [
            ("reviews", REVIEWS_SCHEMA, "ingested_at", ["tenant_id", "upload_id"]),
            ("clusters", CLUSTERS_SCHEMA, "ingested_at", ["tenant_id", "issue_fingerprint"]),
            ("upload_metrics", UPLOAD_METRICS_SCHEMA, "created_at", ["tenant_id"]),
        ]:
            table_ref = dataset_ref.table(table_name)
            try:
                client.get_table(table_ref)
                continue
            except Exception:
                pass

            schema = [bigquery.SchemaField(name, dtype) for name, dtype in schema_fields]
            table = bigquery.Table(table_ref, schema=schema)
            table.time_partitioning = bigquery.TimePartitioning(field=partition_field)
            table.clustering_fields = cluster_by
            client.create_table(table, exists_ok=True)
            logger.info(
                f"Created {self.dataset}.{table_name} "
                f"(partition={partition_field}, cluster={cluster_by})"
            )

    # ------------------------------------------------------------------
    # Batch loads (free, atomic) — the path used for review/cluster volume
    # ------------------------------------------------------------------

    def load_reviews_from_gcs(self, gcs_uri: str, upload_id: int) -> int:
        """
        Load a staged Parquet payload straight from GCS into the reviews
        table via a load job. Idempotent per (upload_id, run): the job
        first deletes any existing rows for this upload_id so a DAG retry
        or backfill replaces rather than duplicates — the property that
        makes the pipeline safely re-runnable.
        """
        from google.cloud import bigquery

        client = self._get_client()
        table_id = self._table_id("reviews")

        # Delete-then-load = idempotent replace for this upload's partition slice.
        client.query(
            f"DELETE FROM `{table_id}` WHERE upload_id = @upload_id",  # noqa: S608 - identifier validated, value parameterized
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("upload_id", "INT64", upload_id)
                ]
            ),
        ).result()

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            # Parquet from GCSStagingStore carries extra columns (raw
            # embedding, feature dicts) that the warehouse deliberately
            # doesn't store — ignore them rather than failing the load.
            ignore_unknown_values=True,
        )

        load_job = client.load_table_from_uri(
            gcs_uri, table_id, job_config=job_config, location=self.location
        )
        result = load_job.result()  # raises on failure — surfaces to Airflow as a task failure
        logger.info(f"Load job {load_job.job_id}: {result.output_rows} rows -> {table_id}")
        return result.output_rows or 0

    def load_reviews(self, upload: Upload, reviews: List[Review]) -> int:
        """
        In-process fallback load (no GCS staging available) — chunks the
        payload into load jobs from local Parquet rather than streaming,
        so it stays free and unquota'd. Prefer load_reviews_from_gcs().
        """
        import io

        import pandas as pd
        from google.cloud import bigquery

        if not reviews:
            return 0

        upload_id = upload.id.value if upload.id else None
        now = datetime.utcnow()

        records = reviews_to_records(reviews)
        df = pd.DataFrame.from_records(records)
        df = df.drop(columns=[c for c in REVIEW_EXCLUDED_COLUMNS if c in df.columns])
        df["upload_id"] = upload_id
        df["ingested_at"] = now

        client = self._get_client()
        table_id = self._table_id("reviews")

        client.query(
            f"DELETE FROM `{table_id}` WHERE upload_id = @upload_id",  # noqa: S608 - identifier validated, value parameterized
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("upload_id", "INT64", upload_id)
                ]
            ),
        ).result()

        buffer = io.BytesIO()
        df.to_parquet(buffer, engine="pyarrow", index=False)
        buffer.seek(0)

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            ignore_unknown_values=True,
        )
        load_job = client.load_table_from_file(
            buffer, table_id, job_config=job_config, location=self.location
        )
        result = load_job.result()
        logger.info(f"Loaded {result.output_rows} reviews -> {table_id}")
        return result.output_rows or 0

    def load_clusters(self, upload: Upload, clusters: List[Cluster]) -> int:
        """
        Load clusters via a load job, computing the stable issue_fingerprint
        each cluster is tracked by across pipeline versions.
        """
        import io

        import pandas as pd
        from google.cloud import bigquery

        if not clusters:
            return 0

        upload_id = upload.id.value if upload.id else None
        now = datetime.utcnow()

        rows = []
        for c in clusters:
            keywords = c.metrics.keywords if c.metrics else []
            rows.append({
                "cluster_id": c.id.value,
                "upload_id": upload_id,
                "tenant_id": str(c.tenant_id.value),
                "title": c.title,
                "issue_fingerprint": compute_issue_fingerprint(c.title, keywords),
                "severity": c.severity.value,
                "status": c.status.value,
                "review_count": c.metrics.review_count if c.metrics else None,
                "avg_rating": c.metrics.avg_rating if c.metrics else None,
                "affected_versions": ",".join(c.metrics.affected_versions) if c.metrics else None,
                "keywords": ",".join(keywords) if keywords else None,
                "ai_analyzed": c.ai_analyzed,
                "created_at": c.created_at,
                "ingested_at": now,
            })

        client = self._get_client()
        table_id = self._table_id("clusters")

        client.query(
            f"DELETE FROM `{table_id}` WHERE upload_id = @upload_id",  # noqa: S608 - identifier validated, value parameterized
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("upload_id", "INT64", upload_id)
                ]
            ),
        ).result()

        buffer = io.BytesIO()
        pd.DataFrame.from_records(rows).to_parquet(buffer, engine="pyarrow", index=False)
        buffer.seek(0)

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            ignore_unknown_values=True,
        )
        load_job = client.load_table_from_file(
            buffer, table_id, job_config=job_config, location=self.location
        )
        result = load_job.result()
        logger.info(f"Loaded {result.output_rows} clusters -> {table_id}")
        return result.output_rows or 0

    def load_upload_metrics(
        self,
        upload: Upload,
        metrics: ProcessingMetrics,
        pipeline_version: str = "v1",
    ) -> None:
        """
        One row per pipeline run, tagged by pipeline_version — the table the
        v1/v2/v3 regression-detection dbt model diffs against. Single row,
        so a streaming insert is the right call here (low latency, no load
        job overhead, negligible cost at one row per run).
        """
        from google.cloud import bigquery

        client = self._get_client()
        table_id = self._table_id("upload_metrics")
        upload_id = upload.id.value if upload.id else None

        # Idempotent: a DAG retry replaces this run's row rather than
        # double-counting it in the regression model.
        client.query(
            f"DELETE FROM `{table_id}` "  # noqa: S608 - identifier validated, values parameterized
            f"WHERE upload_id = @upload_id AND pipeline_version = @pv",
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("upload_id", "INT64", upload_id),
                    bigquery.ScalarQueryParameter("pv", "STRING", pipeline_version),
                ]
            ),
        ).result()

        row = {
            "upload_id": upload_id,
            "tenant_id": str(upload.tenant_id.value),
            "total_reviews": metrics.total_reviews,
            "filtered_noise": metrics.filtered_noise,
            "actionable_reviews": metrics.actionable_reviews,
            "clusters_created": metrics.clusters_created,
            "processing_time_ms": metrics.processing_time_ms,
            "pipeline_version": pipeline_version,
            "created_at": datetime.utcnow().isoformat(),
        }

        errors = client.insert_rows_json(table_id, [row])
        if errors:
            raise RuntimeError(f"Failed to insert upload_metrics: {errors}")
        logger.info(f"Recorded run metrics for upload {upload_id} ({pipeline_version})")
