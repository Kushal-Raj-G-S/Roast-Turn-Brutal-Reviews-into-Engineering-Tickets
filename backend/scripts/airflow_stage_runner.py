"""
Standalone entrypoint for one pipeline stage, run as a SEPARATE PROCESS from
Airflow itself (invoked by airflow/dags/roast_pipeline_dag.py's BashOperator
tasks).

Why this exists, not a direct import from Airflow's own PythonOperator:
Airflow 2.10.5's own ORM models require SQLAlchemy 1.4 (its TaskInstance
model breaks under 2.0's stricter Annotated-Declarative mapping rules,
confirmed by testing -- MappedAnnotationError at Airflow startup). This
backend's SQLModel-based models (app/models/bulk_models.py) require
SQLAlchemy 2.0 the same way (also confirmed by testing -- `cannot import
name 'DOUBLE' from sqlalchemy.types` under 1.4). Two libraries needing
opposite major versions of the same dependency cannot share one Python
process. Running this as its own process, in its own environment (the
backend's normal venv/site-packages, untouched by Airflow's pins), sidesteps
the conflict entirely instead of patching individual missing names forever.

Data handoff: same as the in-process version -- reads the upstream stage's
Parquet from GCS (via GCSStagingStore), writes this stage's own output back,
and instead of Airflow's ti.xcom_push, prints the resulting gs:// URI as the
LAST line of stdout. Airflow's BashOperator (do_xcom_push=True, the default)
captures exactly that last line as the task's XCom return_value, which the
next stage's command pulls via {{ ti.xcom_pull(task_ids='...') }} -- so the
DAG's data-flow contract (URIs through XCom, never raw review payloads) is
unchanged, only the process boundary moved.
"""

import argparse
import asyncio
import sys


def _staging_store():
    from app.core.config import config
    from src.infrastructure.warehouse.gcs_staging import GCSStagingStore

    config.require_gcp()
    return GCSStagingStore(
        bucket=config.GCS_STAGING_BUCKET, project_id=config.GCP_PROJECT_ID
    )


async def _run(args) -> str | None:
    from app.core.pipeline_factory import build_bulk_pipeline
    from src.domain.value_objects import UploadId

    upload_id = UploadId(args.upload_id)
    store = _staging_store()

    async with build_bulk_pipeline() as pipeline:
        upload = await pipeline.upload_repo.get_by_id(upload_id)
        if not upload:
            raise ValueError(f"Upload {args.upload_id} not found")

        def _pull(uri: str):
            if not uri:
                raise ValueError("Missing required --input-uri for this stage")
            return store.read_reviews(uri)

        def _push(reviews) -> str:
            uri = store.write_reviews(reviews, args.upload_id, args.run_id, args.stage)
            print(f"[{args.stage}] wrote {len(reviews)} reviews -> {uri}", file=sys.stderr)
            return uri

        if args.stage == "load_and_validate":
            reviews = await pipeline._load_and_validate_csv(upload)
            return _push(reviews)

        elif args.stage == "filter_noise":
            reviews = await pipeline._filter_noise(upload, _pull(args.input_uri))
            return _push(reviews)

        elif args.stage == "score_actionability":
            reviews = _pull(args.input_uri)
            if pipeline.actionability_scorer:
                reviews = await pipeline._score_actionability(upload, reviews)
            return _push(reviews)

        elif args.stage == "generate_embeddings":
            reviews = await pipeline._generate_embeddings(upload, _pull(args.input_uri))
            return _push(reviews)

        elif args.stage == "cluster_and_rank":
            reviews = _pull(args.input_uri)
            clusters = await pipeline._cluster_reviews(upload, reviews)
            clusters = await pipeline._rank_clusters(upload, clusters)
            saved = await pipeline._persist_clusters(upload, clusters)
            print(f"[cluster_and_rank] persisted {len(saved)} clusters", file=sys.stderr)
            return None

        elif args.stage == "load_warehouse":
            from src.infrastructure.warehouse.bigquery_sink import BigQueryWarehouseSink
            from app.core.config import config

            sink = BigQueryWarehouseSink(
                project_id=config.GCP_PROJECT_ID,
                dataset=config.BIGQUERY_DATASET,
                location=config.BIGQUERY_LOCATION,
            )
            sink.ensure_schema()
            sink.load_reviews_from_gcs(args.embed_uri, args.upload_id)

            clusters = await pipeline.cluster_repo.list_by_upload(upload_id)
            sink.load_clusters(upload, clusters)
            if upload.metrics:
                sink.load_upload_metrics(
                    upload, upload.metrics, pipeline_version=config.PIPELINE_VERSION
                )
            return None

        elif args.stage == "cleanup_staging":
            store.cleanup_run(args.upload_id, args.run_id)
            return None

        else:
            raise ValueError(f"Unknown stage: {args.stage}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--upload-id", required=True, type=int)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--input-uri", default=None)
    parser.add_argument("--embed-uri", default=None)
    args = parser.parse_args()

    output_uri = asyncio.run(_run(args))
    if output_uri:
        # Deliberately the ONLY thing printed to stdout -- this line is what
        # Airflow's BashOperator captures as the task's XCom return_value.
        print(output_uri)


if __name__ == "__main__":
    main()
