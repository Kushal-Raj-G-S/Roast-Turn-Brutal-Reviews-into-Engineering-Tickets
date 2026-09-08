"""
End-to-end test of the event path: real Kafka -> consumer -> real Postgres.

Everything else tests one link. This tests the chain, and specifically the
property the whole design rests on: because delivery is at-least-once, the
same event WILL be delivered more than once, and the side effect must
still happen exactly once.

Requires both the Kafka broker and the throwaway Postgres (see the other
integration test modules for the docker run commands).
"""

import asyncio
import os
import pathlib
import socket
import uuid
from datetime import datetime

import pytest

pytestmark = pytest.mark.integration

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
PG_DSN = os.getenv(
    "TEST_POSTGRES_DSN",
    "postgresql+psycopg2://test:test@localhost:55432/roast_test",
)


def _up(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


pytest.importorskip("aiokafka")
pytest.importorskip("sqlalchemy")

_kafka_host, _, _kafka_port = BOOTSTRAP.partition(":")
if not _up(_kafka_host, int(_kafka_port or 9092)):
    pytest.skip(f"No Kafka at {BOOTSTRAP}", allow_module_level=True)
if not _up("localhost", 55432):
    pytest.skip("No throwaway Postgres at localhost:55432", allow_module_level=True)

from src.infrastructure.messaging.consumers import _claim_event  # noqa: E402
from src.infrastructure.messaging.event_bus import Message  # noqa: E402
from src.infrastructure.messaging.kafka_queue import KafkaQueue  # noqa: E402

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations"
    / "create_processed_events.sql"
)
CONSUMER = "e2e_test_consumer"


@pytest.fixture(scope="module")
def session_factory():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(PG_DSN, future=True)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS processed_events"))
        conn.execute(text(MIGRATION.read_text(encoding="utf-8")))
    return sessionmaker(bind=engine, future=True)


@pytest.mark.asyncio
async def test_event_flows_kafka_to_inbox_and_side_effect_runs_once(session_factory):
    """
    Publish the SAME event three times (simulating at-least-once
    redelivery), and assert the guarded side effect executed exactly once
    while the handler still saw all three deliveries.
    """
    event_type = f"UploadCompletedE2E_{uuid.uuid4().hex[:8]}"
    event_id = str(uuid.uuid4())
    upload_id = 4242

    deliveries = []
    side_effects = []

    queue = KafkaQueue(
        bootstrap_servers=BOOTSTRAP, consumer_group=f"g-{uuid.uuid4().hex[:8]}"
    )

    async def handler(message: Message):
        deliveries.append(message.id)
        # The real consumer's guard, with the test database injected.
        if _claim_event(
            message.id,
            CONSUMER,
            message.event_type,
            int(message.payload["upload_id"]),
            session_factory=session_factory,
        ):
            side_effects.append(message.id)  # stands in for "send the alert"

    await queue.subscribe(event_type, handler)

    for _ in range(3):
        await queue.publish(Message(
            id=event_id,               # same event id => a redelivery
            event_type=event_type,
            payload={"upload_id": str(upload_id)},  # str, as the serializer emits
            timestamp=datetime.utcnow(),
        ))

    await queue.start_consuming()
    try:
        deadline = asyncio.get_event_loop().time() + 30
        while asyncio.get_event_loop().time() < deadline and len(deliveries) < 3:
            await asyncio.sleep(0.25)
    finally:
        await queue.stop_consuming()

    assert len(deliveries) == 3, f"expected 3 deliveries, saw {len(deliveries)}"
    assert len(side_effects) == 1, (
        f"side effect must run exactly once, ran {len(side_effects)}x — "
        "this is the duplicate-notification bug"
    )

    from sqlalchemy import text

    with session_factory() as s:
        rows = s.execute(
            text(
                "SELECT upload_id, event_type FROM processed_events "
                "WHERE event_id = :e AND consumer_name = :c"
            ),
            {"e": event_id, "c": CONSUMER},
        ).all()

    assert len(rows) == 1
    assert rows[0][0] == upload_id
    assert rows[0][1] == event_type


@pytest.mark.asyncio
async def test_distinct_events_each_trigger_their_side_effect(session_factory):
    """Dedup must not over-suppress: different events must each fire."""
    event_type = f"UploadCompletedMulti_{uuid.uuid4().hex[:8]}"
    ids = [str(uuid.uuid4()) for _ in range(4)]
    side_effects = []

    queue = KafkaQueue(
        bootstrap_servers=BOOTSTRAP, consumer_group=f"g-{uuid.uuid4().hex[:8]}"
    )

    async def handler(message: Message):
        if _claim_event(
            message.id, CONSUMER, message.event_type,
            int(message.payload["upload_id"]),
            session_factory=session_factory,
        ):
            side_effects.append(message.id)

    await queue.subscribe(event_type, handler)

    for i, eid in enumerate(ids):
        await queue.publish(Message(
            id=eid,
            event_type=event_type,
            payload={"upload_id": str(100 + i)},
            timestamp=datetime.utcnow(),
        ))

    await queue.start_consuming()
    try:
        deadline = asyncio.get_event_loop().time() + 30
        while asyncio.get_event_loop().time() < deadline and len(side_effects) < 4:
            await asyncio.sleep(0.25)
    finally:
        await queue.stop_consuming()

    assert sorted(side_effects) == sorted(ids), (
        f"all 4 distinct events should fire, got {len(side_effects)}"
    )
