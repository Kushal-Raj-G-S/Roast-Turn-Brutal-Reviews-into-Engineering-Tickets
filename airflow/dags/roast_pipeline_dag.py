"""
Roast bulk-review pipeline DAG.

Why this exists: BulkProcessingPipeline.execute() (see
backend/src/application/use_cases/bulk_processing_pipeline.py) runs
load -> filter -> score -> embed -> cluster -> rank -> persist as one long
async call. That's correct for the interactive API path, but it means a
failure in the clustering stage re-runs the embedding of the whole batch,
there's no backfillable/schedulable entry point, and retry behaviour is
whatever try/except each method happens to have.

This DAG does not reimplement pipeline logic. Each task shells out to
backend/scripts/airflow_stage_runner.py, which calls the SAME stage methods
BulkProcessingPipeline already has -- just from its own process, not
Airflow's. Airflow's retry/backoff and per-task state still take over: a
failed embedding stage retries only that stage, a run can be re-triggered
for a specific upload_id, and every stage's duration is visible in the UI.

WHY A SUBPROCESS, NOT A DIRECT PYTHON IMPORT (PythonOperator):
    Confirmed by testing, not a guess -- Airflow 2.10.5's own ORM models
    require SQLAlchemy 1.4 (its TaskInstance model raises
    MappedAnnotationError under 2.0's stricter mapping rules). This
    backend's SQLModel-based models require SQLAlchemy 2.0 the same way
    (`cannot import name 'DOUBLE' from sqlalchemy.types` under 1.4). Two
    libraries needing opposite major versions of one dependency cannot
    share a process. A small compat shim fixed one such clash
    (async_sessionmaker) but SQLModel's need for 2.0 goes deeper than one
    name -- so backend code runs in its OWN process/environment (the same
    one FastAPI itself runs in) via BashOperator, never imported into
    Airflow's interpreter at all. See infra/docker/Dockerfile.airflow for
    the two-venv image this runs in locally (Airflow isolated in its own
    venv; backend code via the base image's Python, which has the
    backend's real, unconstrained dependency set).

IMPORTANT — how data moves between tasks:
    Payloads are NOT passed through XCom. Airflow persists XCom values in
    its metadata database (48KB limit on the default backend); 200K
    reviews carrying 384-float embeddings is gigabytes and would fail
    outright. Each stage writes Parquet to GCS via GCSStagingStore and
    passes only the gs:// URI through XCom -- airflow_stage_runner.py
    prints it as the last line of stdout, which BashOperator's default
    do_xcom_push=True captures as the task's XCom return_value. That also
    lets BigQuery load the staged Parquet directly with a free batch load
    job.

Local run: see infra/docker/Dockerfile.airflow's docstring-equivalent
comments for the two-venv container this is built and tested against.
In production this is what Cloud Composer runs, pointed at a proper
Docker/KubernetesPodOperator image instead of a bare BashOperator.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.trigger_rule import TriggerRule

default_args = {
    "owner": "roast",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=20),
    "depends_on_past": False,
}

STAGE_LOAD = "load_and_validate"
STAGE_FILTER = "filter_noise"
STAGE_SCORE = "score_actionability"
STAGE_EMBED = "generate_embeddings"
STAGE_CLUSTER = "cluster_and_rank"
STAGE_WAREHOUSE = "load_warehouse"
STAGE_CLEANUP = "cleanup_staging"

# The Python that has the backend's real dependencies (SQLAlchemy 2.0,
# SQLModel, torch, faiss, ...) -- the base image's interpreter, deliberately
# NOT the venv `airflow` itself runs in. Override via env for other setups
# (e.g. a Windows host running the DAG against a venv path instead).
import os

BACKEND_PYTHON = os.environ.get("ROAST_BACKEND_PYTHON", "python")
RUNNER_SCRIPT = os.environ.get(
    "ROAST_STAGE_RUNNER", "/opt/airflow/backend/scripts/airflow_stage_runner.py"
)
# The backend resolves some paths relative to its own root (e.g. an upload's
# stored path like ./uploads/1.csv). BashOperator otherwise runs from a temp
# cwd, so every stage runs with the backend root as its working directory.
BACKEND_CWD = os.environ.get("ROAST_BACKEND_CWD", "/opt/airflow/backend")

_UPLOAD_ID = "{{ dag_run.conf['upload_id'] }}"
_RUN_ID = "{{ run_id }}"


def _cmd(stage: str, input_task: str | None = None, embed_task: str | None = None) -> str:
    """Build the BashOperator command for one stage."""
    parts = [
        BACKEND_PYTHON,
        RUNNER_SCRIPT,
        "--stage", stage,
        "--upload-id", _UPLOAD_ID,
        "--run-id", _RUN_ID,
    ]
    if input_task:
        parts += ["--input-uri", f"{{{{ ti.xcom_pull(task_ids='{input_task}') }}}}"]
    if embed_task:
        parts += ["--embed-uri", f"{{{{ ti.xcom_pull(task_ids='{embed_task}') }}}}"]
    return " ".join(parts)


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

    load_and_validate = BashOperator(
        task_id=STAGE_LOAD,
        bash_command=_cmd(STAGE_LOAD),
        cwd=BACKEND_CWD,
    )

    filter_noise = BashOperator(
        task_id=STAGE_FILTER,
        bash_command=_cmd(STAGE_FILTER, input_task=STAGE_LOAD),
        cwd=BACKEND_CWD,
    )

    score_actionability = BashOperator(
        task_id=STAGE_SCORE,
        bash_command=_cmd(STAGE_SCORE, input_task=STAGE_FILTER),
        cwd=BACKEND_CWD,
    )

    generate_embeddings = BashOperator(
        task_id=STAGE_EMBED,
        bash_command=_cmd(STAGE_EMBED, input_task=STAGE_SCORE),
        # The slow CPU-bound stage — give it room, and its own retry budget.
        execution_timeout=timedelta(hours=2),
        retries=5,
        cwd=BACKEND_CWD,
    )

    cluster_and_rank = BashOperator(
        task_id=STAGE_CLUSTER,
        bash_command=_cmd(STAGE_CLUSTER, input_task=STAGE_EMBED),
        cwd=BACKEND_CWD,
    )

    load_warehouse = BashOperator(
        task_id=STAGE_WAREHOUSE,
        bash_command=_cmd(STAGE_WAREHOUSE, embed_task=STAGE_EMBED),
        cwd=BACKEND_CWD,
    )

    cleanup_staging = BashOperator(
        task_id=STAGE_CLEANUP,
        bash_command=_cmd(STAGE_CLEANUP),
        trigger_rule=TriggerRule.ALL_SUCCESS,
        cwd=BACKEND_CWD,
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
