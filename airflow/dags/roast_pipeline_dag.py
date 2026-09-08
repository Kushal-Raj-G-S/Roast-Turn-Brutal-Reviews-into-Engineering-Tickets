"""
Roast bulk-review pipeline DAG.

Why this exists: BulkProcessingPipeline.execute() (see
backend/src/application/use_cases/bulk_processing_pipeline.py) runs
load -> filter -> score -> embed -> cluster -> rank -> persist as one long
async call. That's correct for the interactive API path, but it means a
failure in the clustering stage re-runs the embedding of the whole batch,
there's no backfillable/schedulable entry point, and retry behaviour is
whatever try/except each method happens to have.

This DAG does not reimplement pipeline logic. It calls the SAME stage
methods as discrete Airflow tasks so Airflow's retry/backoff and per-task
state take over: a failed embedding stage retries only that stage, a run
can be re-triggered for a specific upload_id, and every stage's duration
is visible in the UI.

IMPORTANT — how data moves between tasks:
    Payloads are NOT passed through XCom. Airflow persists XCom values in
    its metadata database (48KB limit on the default backend); 200K
    reviews carrying 384-float embeddings is gigabytes and would fail
    outright. Each stage writes Parquet to GCS via GCSStagingStore and
    passes only the gs:// URI through XCom. That also lets BigQuery load
    the staged Parquet directly with a free batch load job.

Local run: `pip install apache-airflow` then `airflow standalone`
(ships its own SQLite metadata DB — nothing external to install).
In production this is what Cloud Composer runs unmodified.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

default_args = {
    "owner": "roast",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=20),
    "depends_on_past": False,
}

# Stage name -> the XCom key holding its output URI
STAGE_LOAD = "load_and_validate"
STAGE_FILTER = "filter_noise"
STAGE_SCORE = "score_actionability"
STAGE_EMBED = "generate_embeddings"
STAGE_CLUSTER = "cluster_and_rank"
STAGE_WAREHOUSE = "load_warehouse"
STAGE_CLEANUP = "cleanup_staging"


def _ensure_backend_on_path():
    """The DAG process is separate from the FastAPI app, so it needs the
    same sys.path entry the app gets from running uvicorn inside backend/."""
    import sys
    from pathlib import Path

    backend_dir = str(Path(__file__).resolve().parents[2] / "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


def _staging_store():
    from app.core.config import config
    from src.infrastructure.warehouse.gcs_staging import GCSStagingStore

    config.require_gcp()
    return GCSStagingStore(
        bucket=config.GCS_STAGING_BUCKET, project_id=config.GCP_PROJECT_ID
    )


async def _run_one_stage(stage_name: str, upload_id, run_id: str, ti) -> None:
    """
    Runs one named stage against a freshly-built pipeline, reading the
    upstream stage's Parquet from GCS and writing this stage's output back.
    Calls into BulkProcessingPipeline's existing stage methods unmodified.
    """
    from app.core.config import config
    from app.core.pipeline_factory import build_bulk_pipeline

    store = _staging_store()
    raw_upload_id = upload_id.value

    async with build_bulk_pipeline() as pipeline:
        upload = await pipeline.upload_repo.get_by_id(upload_id)
        if not upload:
            raise ValueError(f"Upload {upload_id} not found")

        def _pull(stage: str):
            uri = ti.xcom_pull(task_ids=stage, key="staged_uri")
            if not uri:
                raise ValueError(f"No staged output found from upstream stage '{stage}'")
            return store.read_reviews(uri)

        def _push(reviews) -> None:
            uri = store.write_reviews(reviews, raw_upload_id, run_id, stage_name)
            ti.xcom_push(key="staged_uri", value=uri)
            ti.xcom_push(key="review_count", value=len(reviews))

        if stage_name == STAGE_LOAD:
            reviews = await pipeline._load_and_validate_csv(upload)
            _push(reviews)

        elif stage_name == STAGE_FILTER:
            reviews = await pipeline._filter_noise(upload, _pull(STAGE_LOAD))
            _push(reviews)

        elif stage_name == STAGE_SCORE:
            reviews = _pull(STAGE_FILTER)
            if pipeline.actionability_scorer:
                reviews = await pipeline._score_actionability(upload, reviews)
            _push(reviews)

        elif stage_name == STAGE_EMBED:
            reviews = await pipeline._generate_embeddings(upload, _pull(STAGE_SCORE))
            _push(reviews)

        elif stage_name == STAGE_CLUSTER:
            reviews = _pull(STAGE_EMBED)
            clusters = await pipeline._cluster_reviews(upload, reviews)
            clusters = await pipeline._rank_clusters(upload, clusters)
            saved = await pipeline._persist_clusters(upload, clusters)
            ti.xcom_push(key="cluster_count", value=len(saved))

        elif stage_name == STAGE_WAREHOUSE:
            # Warehouse sync is its own task so a BigQuery failure never
            # rolls back the user-facing Postgres write that already
            # succeeded upstream.
            from src.infrastructure.warehouse.bigquery_sink import BigQueryWarehouseSink

            sink = BigQueryWarehouseSink(
                project_id=config.GCP_PROJECT_ID,
                dataset=config.BIGQUERY_DATASET,
                location=config.BIGQUERY_LOCATION,
            )
            sink.ensure_schema()

            # Load reviews straight from the staged Parquet — free batch
            # load job, no re-serialization, idempotent per upload_id.
            embed_uri = ti.xcom_pull(task_ids=STAGE_EMBED, key="staged_uri")
            sink.load_reviews_from_gcs(embed_uri, raw_upload_id)

            clusters = await pipeline.cluster_repo.list_by_upload(upload_id)
            sink.load_clusters(upload, clusters)

            if upload.metrics:
                sink.load_upload_metrics(
                    upload, upload.metrics, pipeline_version=config.PIPELINE_VERSION
                )

        else:
            raise ValueError(f"Unknown stage: {stage_name}")


def _run_stage(stage_name: str, **context):
    """Task entrypoint: resolves upload_id from the DAG run config and runs the stage."""
    import asyncio

    upload_id_raw = context["dag_run"].conf.get("upload_id")
    if upload_id_raw is None:
        raise ValueError("DAG run must be triggered with {'upload_id': <id>} in conf")

    _ensure_backend_on_path()
    from src.domain.value_objects import UploadId

    asyncio.run(
        _run_one_stage(
            stage_name,
            UploadId(int(upload_id_raw)),
            context["run_id"],
            context["ti"],
        )
    )


def _cleanup_staging(**context):
    """
    Delete this run's staged Parquet so successful runs don't accumulate
    storage cost. Runs only when every upstream task succeeded — a failed
    run keeps its artifacts for post-mortem inspection, which is the whole
    point of staging to durable storage in the first place.
    """
    upload_id_raw = context["dag_run"].conf.get("upload_id")
    _ensure_backend_on_path()
    store = _staging_store()
    store.cleanup_run(int(upload_id_raw), context["run_id"])


with DAG(
    dag_id="roast_bulk_review_pipeline",
    description="Ingest -> filter -> score -> embed -> cluster -> persist -> warehouse -> dbt",
    default_args=default_args,
    schedule=None,  # triggered per-upload by the API, or manually for backfill
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=3,  # bound concurrent embedding load on the cluster
    tags=["roast", "review-pipeline"],
) as dag:

    load_and_validate = PythonOperator(
        task_id=STAGE_LOAD,
        python_callable=_run_stage,
        op_kwargs={"stage_name": STAGE_LOAD},
    )

    filter_noise = PythonOperator(
        task_id=STAGE_FILTER,
        python_callable=_run_stage,
        op_kwargs={"stage_name": STAGE_FILTER},
    )

    score_actionability = PythonOperator(
        task_id=STAGE_SCORE,
        python_callable=_run_stage,
        op_kwargs={"stage_name": STAGE_SCORE},
    )

    generate_embeddings = PythonOperator(
        task_id=STAGE_EMBED,
        python_callable=_run_stage,
        op_kwargs={"stage_name": STAGE_EMBED},
        # The slow CPU-bound stage — give it room, and its own retry budget.
        execution_timeout=timedelta(hours=2),
        retries=5,
    )

    cluster_and_rank = PythonOperator(
        task_id=STAGE_CLUSTER,
        python_callable=_run_stage,
        op_kwargs={"stage_name": STAGE_CLUSTER},
    )

    load_warehouse = PythonOperator(
        task_id=STAGE_WAREHOUSE,
        python_callable=_run_stage,
        op_kwargs={"stage_name": STAGE_WAREHOUSE},
    )

    cleanup_staging = PythonOperator(
        task_id=STAGE_CLEANUP,
        python_callable=_cleanup_staging,
        trigger_rule=TriggerRule.ALL_SUCCESS,
    )

    (
        load_and_validate
        >> filter_noise
        >> score_actionability
        >> generate_embeddings
        >> cluster_and_rank
        >> load_warehouse
        >> cleanup_staging
    )
