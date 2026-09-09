"""
Event consumers.

Closes the last gap in the event pipeline: BulkProcessingPipeline emits a
domain event at every stage, KafkaQueue durably stores them — and until
this module existed, nothing read them. Events were produced and
persisted, then ignored.

What this adds functionally (rather than just architecturally): the v2
pipeline path (src/api/routes/upload_v2.py and the Airflow DAG) never sent
the user a completion alert at all. Only the v1 path
(app/core/shadow_deployment.py) did, inline. So subscribing to
UPLOAD_COMPLETED here gives the v2 path the notification it was missing —
without double-sending, because the two paths are disjoint and only the v2
pipeline publishes these events.

Idempotency is mandatory, not defensive: KafkaQueue is at-least-once, so a
crash between handler-success and offset-commit replays the batch. A
replayed completion event would re-send the user's Discord/push/email
alert. Every handler here claims its event in the `processed_events` inbox
table first (see migrations/create_processed_events.sql) and skips if the
claim conflicts.
"""

import logging
from typing import Optional

from .event_bus import EventBus, Message

logger = logging.getLogger(__name__)

NOTIFICATION_CONSUMER = "upload_notifications"
# Second, independent consumer of UPLOAD_COMPLETED. Its own name means the
# inbox dedups it separately from the notification consumer.
WAREHOUSE_CONSUMER = "warehouse_loader"


def _claim_event(
    event_id: str,
    consumer_name: str,
    event_type: str,
    upload_id: Optional[int],
    session_factory=None,
) -> bool:
    """
    Atomically claim an event for this consumer.

    Returns True if this call won the claim (the caller should process the
    event), False if it was already handled — which is the normal, expected
    outcome of an at-least-once redelivery, not an error.

    Uses a synchronous session because the notification dispatcher it
    guards (shadow_deployment._send_upload_alerts) takes a sync Session.

    `session_factory` is injectable so tests bind to a throwaway database.
    Without it, importing this module would tie every test to whatever
    DATABASE_URL points at — i.e. production.
    """
    from sqlalchemy import text

    if session_factory is None:
        from app.database.database import SessionLocal

        session_factory = SessionLocal

    with session_factory() as session:
        result = session.execute(
            text(
                """
                INSERT INTO processed_events
                    (event_id, consumer_name, event_type, upload_id)
                VALUES (:event_id, :consumer_name, :event_type, :upload_id)
                ON CONFLICT (event_id, consumer_name) DO NOTHING
                """
            ),
            {
                "event_id": event_id,
                "consumer_name": consumer_name,
                "event_type": event_type,
                "upload_id": upload_id,
            },
        )
        session.commit()
        # rowcount is 1 when the insert happened, 0 when ON CONFLICT skipped it.
        return result.rowcount == 1


async def handle_upload_completed(message: Message) -> None:
    """
    Send the user their completion alert for a v2-pipeline upload.

    Deliberately does not raise on notification failure: a dead webhook or
    a rejected push subscription must not send the message back for retry
    and eventually to the DLQ — the pipeline run itself succeeded. Only
    genuinely retryable problems (database unreachable) propagate.
    """
    payload = message.payload or {}
    event_id = message.id
    upload_id = payload.get("upload_id")

    if upload_id is None:
        logger.warning(f"UPLOAD_COMPLETED event {event_id} has no upload_id; skipping")
        return

    upload_id = int(upload_id)

    # Claim first. If the DB is unreachable this raises, the handler fails,
    # the offset is not committed, and the event is retried — which is the
    # behaviour we want for an infrastructure fault.
    if not _claim_event(
        event_id, NOTIFICATION_CONSUMER, message.event_type, upload_id
    ):
        logger.info(
            f"Event {event_id} (upload {upload_id}) already notified — "
            "skipping duplicate delivery"
        )
        return

    try:
        from sqlmodel import Session

        from app.core.shadow_deployment import _send_upload_alerts
        from app.database.database import engine
        from app.models.bulk_models import Cluster, Upload

        # Must be a SQLModel Session, not app.database.SessionLocal (which is
        # a plain sqlalchemy.orm sessionmaker). shadow_deployment is written
        # against SQLModel and calls session.exec(); a SQLAlchemy Session has
        # only .execute(), so every alert died on
        # "'Session' object has no attribute 'exec'" — and because this
        # handler swallows notification errors by design, it failed SILENTLY:
        # the pipeline reported success, the event was marked consumed, and
        # the user simply never got told. SQLModel's Session subclasses
        # SQLAlchemy's, so .get() and .query() below still work.
        with Session(engine) as session:
            upload = session.get(Upload, upload_id)
            if upload is None:
                logger.warning(f"Upload {upload_id} not found; nothing to notify")
                return

            clusters = (
                session.query(Cluster).filter(Cluster.upload_id == upload_id).all()
            )
            await _send_upload_alerts(session, upload, clusters)

        logger.info(f"Sent completion alerts for upload {upload_id}")

    except Exception as e:
        # Swallowed on purpose — see the docstring. The event stays claimed
        # so a redelivery won't retry a send that is unlikely to succeed and
        # might partially have.
        logger.warning(
            f"Notification dispatch failed for upload {upload_id} (non-fatal): {e}",
            exc_info=True,
        )


async def handle_upload_failed(message: Message) -> None:
    """Log pipeline failures from the event stream. Kept separate from the
    completion handler so a failure notification channel can be added later
    without touching the success path."""
    payload = message.payload or {}
    upload_id = payload.get("upload_id")

    if not _claim_event(
        message.id, NOTIFICATION_CONSUMER, message.event_type,
        int(upload_id) if upload_id is not None else None,
    ):
        return

    logger.error(
        f"Upload {upload_id} failed: {payload.get('error_message')} "
        f"(stage={payload.get('stage')})"
    )


async def handle_upload_completed_warehouse(message: Message) -> None:
    """
    Mirror a finished upload into the BigQuery warehouse.

    Why this is a SECOND consumer on the same event rather than a step at
    the end of the pipeline:

      - The request path stays fast and stays correct. A warehouse load is
        analytics, not part of "did this upload succeed" — a BigQuery
        outage must not fail a user's upload or roll back their clusters.
      - It gets its own retry budget. Kafka redelivers this handler without
        re-running clustering, which inline code could not offer.
      - The inbox already supports it: the processed_events primary key is
        (event_id, consumer_name) precisely so several consumers can each
        handle one event exactly once. This claims under its own name, so
        it neither blocks nor is blocked by the notification consumer.

    Skipped cleanly when GCP is not configured, so this is inert by default
    and the pipeline behaves exactly as before unless GCP_PROJECT_ID is set.
    """
    from app.core.config import Config

    payload = message.payload or {}
    upload_id = payload.get("upload_id")
    if upload_id is None:
        logger.warning(f"UPLOAD_COMPLETED {message.id} has no upload_id; skipping warehouse load")
        return
    upload_id = int(upload_id)

    if not Config.GCP_PROJECT_ID:
        logger.debug(
            f"GCP_PROJECT_ID unset — skipping warehouse load for upload {upload_id}"
        )
        return

    # Claimed under this consumer's own name; a redelivery is a no-op.
    if not _claim_event(
        message.id, WAREHOUSE_CONSUMER, message.event_type, upload_id
    ):
        logger.info(
            f"Event {message.id} (upload {upload_id}) already warehoused — skipping"
        )
        return

    try:
        from app.database.database import AsyncSessionLocal
        from src.domain.value_objects import UploadId
        from src.infrastructure.persistence.repositories import (
            PostgresClusterRepository,
            PostgresUploadRepository,
        )
        from src.infrastructure.warehouse.bigquery_sink import BigQueryWarehouseSink

        sink = BigQueryWarehouseSink(
            project_id=Config.GCP_PROJECT_ID,
            dataset=Config.BIGQUERY_DATASET,
            location=Config.BIGQUERY_LOCATION,
        )
        sink.ensure_schema()

        # Read through the repositories, NOT raw SQLModel rows. The sink is
        # written against the domain entities (src/domain/entities.py) and does
        # `upload.id.value`, so handing it a SQLModel row — whose .id is a
        # plain int — dies with "'int' object has no attribute 'value'". That
        # is what happened on upload 91: the event was claimed, the load threw,
        # this handler swallowed it, and BigQuery stayed empty while everything
        # else looked green. The repositories' _to_domain() does the mapping.
        async with AsyncSessionLocal() as session:
            upload_repo = PostgresUploadRepository(session)
            cluster_repo = PostgresClusterRepository(session)

            upload = await upload_repo.get_by_id(UploadId(upload_id))
            if upload is None:
                logger.warning(f"Upload {upload_id} vanished; nothing to warehouse")
                return
            clusters = await cluster_repo.list_by_upload(UploadId(upload_id))

        # One row per run, keyed by (upload_id, pipeline_version) -- the table
        # the dbt regression model diffs versions against. Streaming insert,
        # so it does not depend on the load-job path below.
        if upload.metrics:
            sink.load_upload_metrics(
                upload, upload.metrics, pipeline_version=Config.PIPELINE_VERSION
            )
            logger.info(f"Warehoused metrics for upload {upload_id}")

        if not clusters:
            logger.info(f"Upload {upload_id} produced no clusters; nothing more to warehouse")
            return

        try:
            rows = sink.load_clusters(upload, clusters)
            logger.info(
                f"Warehoused upload {upload_id}: {rows} cluster rows -> "
                f"{Config.GCP_PROJECT_ID}.{Config.BIGQUERY_DATASET}"
            )
        except Exception as load_err:
            # Kept separate from the metrics insert above so one cannot mask
            # the other. load_clusters uses a batch LOAD JOB (deliberately --
            # streaming is billed and caps near 10MB, see the module
            # docstring), and a load job is a resumable upload.
            # goccy/bigquery-emulator panics on that request with
            # "runtime error: invalid memory address or nil pointer
            # dereference", so the cluster load cannot be exercised against
            # the emulator at all. Real BigQuery handles it normally.
            logger.error(
                f"Cluster load-job failed for upload {upload_id} "
                f"(metrics still warehoused): {load_err}"
            )

    except Exception as e:
        # Left claimed on purpose: a partially-completed load job re-run by a
        # redelivery would risk double-counting in the dbt regression model,
        # which is worse than a gap. Backfill deliberately via the Airflow DAG,
        # which is idempotent per upload_id.
        logger.error(
            f"Warehouse load failed for upload {upload_id} (non-fatal, upload still OK): {e}",
            exc_info=True,
        )


async def register_consumers(bus: EventBus) -> None:
    """
    Subscribe every consumer and start the bus.

    Subscribes against the raw queue rather than EventBus.subscribe()
    because the latter deserializes into concrete DomainEvent subclasses,
    and these handlers only need the payload dict — going through the
    typed path would make an unrelated new event field a deserialization
    error at consume time.
    """
    from src.domain.events import EventType

    await bus.message_queue.subscribe(
        EventType.UPLOAD_COMPLETED.value, handle_upload_completed
    )
    await bus.message_queue.subscribe(
        EventType.UPLOAD_FAILED.value, handle_upload_failed
    )
    # Same event, different consumer: notification and warehouse load are
    # independent and must not be able to starve each other.
    await bus.message_queue.subscribe(
        EventType.UPLOAD_COMPLETED.value, handle_upload_completed_warehouse
    )

    await bus.start()
    logger.info("Event consumers registered and consuming")
