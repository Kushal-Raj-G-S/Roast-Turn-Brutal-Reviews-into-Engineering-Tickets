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

    await bus.start()
    logger.info("Event consumers registered and consuming")
