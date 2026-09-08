"""
GCS Parquet staging store for inter-stage pipeline handoff.

Why this exists (this is the fix for a real production blocker):
    Airflow XCom persists task return values in the Airflow *metadata
    database*. Passing the review list between DAG stages via XCom means
    writing 200K reviews — each carrying a 384-dimension float embedding
    — into metadata DB rows. That's multiple GB per run, and XCom has a
    hard size limit (48KB on the default backend). It does not just run
    slowly; it fails.

    The standard production pattern is: stages write their payload to
    object storage and pass only the *URI* through XCom. That's what this
    does. It also gives Roast a real data-lake staging layer — the
    Parquet files are directly loadable by BigQuery batch load jobs
    (free) rather than streaming inserts (billed, quota-limited).

Layout:
    gs://<bucket>/staging/upload=<id>/run=<dag_run_id>/<stage>.parquet

Columnar Parquet (not JSON) because embeddings compress well as a
list<float> column and BigQuery loads Parquet natively without a schema
declaration.

Requires: pip install google-cloud-storage pyarrow
"""

import io
import logging
from typing import List, Optional

import pandas as pd

from ...domain.entities import Review
from .review_codec import records_to_reviews, reviews_to_records

logger = logging.getLogger(__name__)


class GCSStagingStore:
    """Writes/reads per-stage Parquet payloads to GCS, returning gs:// URIs."""

    def __init__(self, bucket: str, project_id: Optional[str] = None, prefix: str = "staging"):
        self.bucket_name = bucket
        self.project_id = project_id
        self.prefix = prefix
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google.cloud import storage
            self._client = storage.Client(project=self.project_id)
        return self._client

    def _blob_path(self, upload_id: int, run_id: str, stage: str) -> str:
        # run_id is included so a re-run (backfill) never overwrites the
        # artifacts of the original run — you can diff them afterwards.
        safe_run = str(run_id).replace(":", "-").replace("+", "-")
        return f"{self.prefix}/upload={upload_id}/run={safe_run}/{stage}.parquet"

    def uri(self, upload_id: int, run_id: str, stage: str) -> str:
        return f"gs://{self.bucket_name}/{self._blob_path(upload_id, run_id, stage)}"

    def write_reviews(
        self,
        reviews: List[Review],
        upload_id: int,
        run_id: str,
        stage: str,
    ) -> str:
        """Serialize reviews to Parquet in GCS. Returns the gs:// URI to pass via XCom."""
        records = reviews_to_records(reviews)
        df = pd.DataFrame.from_records(records)

        buffer = io.BytesIO()
        df.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
        buffer.seek(0)

        blob_path = self._blob_path(upload_id, run_id, stage)
        bucket = self._get_client().bucket(self.bucket_name)
        bucket.blob(blob_path).upload_from_file(
            buffer, content_type="application/octet-stream"
        )

        uri = f"gs://{self.bucket_name}/{blob_path}"
        logger.info(f"Staged {len(reviews)} reviews ({stage}) -> {uri}")
        return uri

    def read_reviews(self, uri: str) -> List[Review]:
        """Read a staged Parquet payload back into Review entities."""
        blob_path = uri.replace(f"gs://{self.bucket_name}/", "")
        bucket = self._get_client().bucket(self.bucket_name)

        buffer = io.BytesIO()
        bucket.blob(blob_path).download_to_file(buffer)
        buffer.seek(0)

        df = pd.read_parquet(buffer, engine="pyarrow")
        reviews = records_to_reviews(df.to_dict(orient="records"))
        logger.info(f"Loaded {len(reviews)} reviews from {uri}")
        return reviews

    def cleanup_run(self, upload_id: int, run_id: str) -> int:
        """
        Delete a run's staged artifacts. Called by the DAG's final task so
        successful runs don't accumulate storage cost — failed runs keep
        their artifacts for post-mortem inspection.
        """
        safe_run = str(run_id).replace(":", "-").replace("+", "-")
        prefix = f"{self.prefix}/upload={upload_id}/run={safe_run}/"
        bucket = self._get_client().bucket(self.bucket_name)

        deleted = 0
        for blob in self._get_client().list_blobs(bucket, prefix=prefix):
            blob.delete()
            deleted += 1
        logger.info(f"Cleaned up {deleted} staged artifacts for run {run_id}")
        return deleted
