"""
Integration tests for KafkaQueue against a REAL Kafka broker.

These are the tests that actually prove the claims in
docs/PLATFORM_REARCHITECTURE.md. The unit tests only verify the port is
implemented and topics are named correctly — they never open a socket, so
they cannot tell you whether publish/consume, offset commits, retry, or
dead-letter routing work at all.

Run with a broker available:

    docker run -d --name roast-kafka-test -p 9092:9092 \
      -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller \
      -e KAFKA_LISTENERS=PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093 \
      -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
      -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
      -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT \
      -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
      -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
      -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
      -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
      -e KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0 \
      apache/kafka:3.8.0

    pytest tests/integration/ -v -m integration

Skipped automatically when no broker is reachable, so the default unit
run stays fast and offline.
"""

import asyncio
import os
import socket
import uuid
from datetime import datetime

import pytest

from src.infrastructure.messaging.event_bus import Message
from src.infrastructure.messaging.kafka_queue import KafkaQueue

pytestmark = pytest.mark.integration

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def _broker_reachable() -> bool:
    host, _, port = BOOTSTRAP.partition(":")
    try:
        with socket.create_connection((host, int(port or 9092)), timeout=3):
            return True
    except OSError:
        return False


pytest.importorskip("aiokafka", reason="aiokafka not installed")

if not _broker_reachable():
    pytest.skip(
        f"No Kafka broker reachable at {BOOTSTRAP}", allow_module_level=True
    )


def _message(event_type: str, payload: dict, max_retries: int = 3) -> Message:
    return Message(
        id=str(uuid.uuid4()),
        event_type=event_type,
        payload=payload,
        timestamp=datetime.utcnow(),
        max_retries=max_retries,
    )


async def _drain(queue: KafkaQueue, predicate, timeout: float = 30.0):
    """
    Start consuming and wait until `predicate()` is true or timeout.
    Polling rather than a fixed sleep so the test is not timing-fragile.
    """
    await queue.start_consuming()
    try:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if predicate():
                return True
            await asyncio.sleep(0.25)
        return predicate()
    finally:
        await queue.stop_consuming()


@pytest.mark.asyncio
async def test_publish_and_consume_round_trip():
    """A published message is actually delivered to a subscribed handler."""
    event_type = f"RoundTripEvent_{uuid.uuid4().hex[:8]}"
    received = []

    queue = KafkaQueue(bootstrap_servers=BOOTSTRAP, consumer_group=f"g-{uuid.uuid4().hex[:8]}")

    async def handler(message: Message):
        received.append(message)

    await queue.subscribe(event_type, handler)

    sent = _message(event_type, {"upload_id": 123, "stage": "embedding"})
    await queue.publish(sent)

    assert await _drain(queue, lambda: len(received) >= 1), "message never arrived"

    got = received[0]
    assert got.id == sent.id
    assert got.event_type == event_type
    assert got.payload["upload_id"] == 123
    assert got.payload["stage"] == "embedding"


@pytest.mark.asyncio
async def test_handler_failure_retries_then_succeeds():
    """
    A transient handler failure is retried via republish with an
    incremented counter, and eventually succeeds — proving the retry path
    works end to end rather than merely being written.
    """
    event_type = f"RetryEvent_{uuid.uuid4().hex[:8]}"
    attempts = []

    queue = KafkaQueue(bootstrap_servers=BOOTSTRAP, consumer_group=f"g-{uuid.uuid4().hex[:8]}")

    async def flaky_handler(message: Message):
        attempts.append(message.retry_count)
        if len(attempts) < 3:
            raise RuntimeError("transient failure")

    await queue.subscribe(event_type, flaky_handler)
    await queue.publish(_message(event_type, {"n": 1}, max_retries=5))

    assert await _drain(queue, lambda: len(attempts) >= 3), (
        f"expected >=3 attempts, saw {attempts}"
    )
    # Retry counter must actually advance, otherwise retries are infinite.
    assert attempts[0] == 0
    assert attempts[1] == 1
    assert attempts[2] == 2


@pytest.mark.asyncio
async def test_exhausted_retries_go_to_dead_letter_topic():
    """
    THE important failure-path test: a permanently-failing message must
    land on <topic>.dlq and must NOT be republished onto the source topic
    forever (the bug the first version of this code had).
    """
    event_type = f"PoisonEvent_{uuid.uuid4().hex[:8]}"
    attempts = []

    queue = KafkaQueue(bootstrap_servers=BOOTSTRAP, consumer_group=f"g-{uuid.uuid4().hex[:8]}")

    async def always_fails(message: Message):
        attempts.append(message.retry_count)
        raise RuntimeError("permanent failure")

    await queue.subscribe(event_type, always_fails)
    await queue.publish(_message(event_type, {"poison": True}, max_retries=2))

    # 3 deliveries total: initial (retry_count 0) + 2 retries.
    await _drain(queue, lambda: len(attempts) >= 3, timeout=30)

    # Now read the DLQ directly and confirm the message is there, tagged.
    import json

    from aiokafka import AIOKafkaConsumer

    dlq_topic = queue._dlq_for(event_type)
    consumer = AIOKafkaConsumer(
        dlq_topic,
        bootstrap_servers=BOOTSTRAP,
        group_id=f"dlq-reader-{uuid.uuid4().hex[:8]}",
        value_deserializer=lambda v: json.loads(v.decode()),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()
    try:
        dlq_records = []
        deadline = asyncio.get_event_loop().time() + 20
        while asyncio.get_event_loop().time() < deadline and not dlq_records:
            batches = await consumer.getmany(timeout_ms=1000)
            for records in batches.values():
                dlq_records.extend(records)
    finally:
        await consumer.stop()

    assert dlq_records, f"nothing landed on the DLQ topic {dlq_topic}"

    envelope = dlq_records[0].value
    assert envelope["dead_letter"] is True
    assert envelope["payload"]["poison"] is True
    assert "permanent failure" in envelope["error"]
    assert "failed_at" in envelope
    # Retries must be bounded — not an infinite loop.
    assert len(attempts) <= 4, f"retried too many times: {attempts}"


@pytest.mark.asyncio
async def test_consumer_group_offsets_persist_across_restart():
    """
    Durability claim: a restarted consumer in the same group resumes after
    committed offsets instead of reprocessing everything. This is the
    property Kafka was chosen for over the in-memory queue.
    """
    event_type = f"OffsetEvent_{uuid.uuid4().hex[:8]}"
    group = f"g-{uuid.uuid4().hex[:8]}"

    first_pass = []
    producer_queue = KafkaQueue(bootstrap_servers=BOOTSTRAP, consumer_group=group)
    for i in range(3):
        await producer_queue.publish(_message(event_type, {"n": i}))

    q1 = KafkaQueue(bootstrap_servers=BOOTSTRAP, consumer_group=group)

    async def h1(message: Message):
        first_pass.append(message.payload["n"])

    await q1.subscribe(event_type, h1)
    await _drain(q1, lambda: len(first_pass) >= 3)
    assert sorted(first_pass) == [0, 1, 2], f"first pass got {first_pass}"

    # Same group, fresh consumer — should see nothing new, because the
    # first consumer committed its offsets.
    second_pass = []
    q2 = KafkaQueue(bootstrap_servers=BOOTSTRAP, consumer_group=group)

    async def h2(message: Message):
        second_pass.append(message.payload["n"])

    await q2.subscribe(event_type, h2)
    await _drain(q2, lambda: False, timeout=8)  # just poll for a while

    assert second_pass == [], (
        f"offsets were not committed — reprocessed {second_pass}"
    )

    await producer_queue.stop_consuming()


@pytest.mark.asyncio
async def test_message_key_preserves_per_entity_ordering():
    """
    Events are keyed by message id so all events for one entity share a
    partition and stay ordered. Verify ordering holds for a single key.
    """
    event_type = f"OrderEvent_{uuid.uuid4().hex[:8]}"
    received = []

    queue = KafkaQueue(bootstrap_servers=BOOTSTRAP, consumer_group=f"g-{uuid.uuid4().hex[:8]}")

    async def handler(message: Message):
        received.append(message.payload["seq"])

    await queue.subscribe(event_type, handler)

    shared_id = str(uuid.uuid4())
    for seq in range(5):
        await queue.publish(Message(
            id=shared_id,  # same key -> same partition
            event_type=event_type,
            payload={"seq": seq},
            timestamp=datetime.utcnow(),
        ))

    assert await _drain(queue, lambda: len(received) >= 5), f"only got {received}"
    assert received[:5] == [0, 1, 2, 3, 4], f"ordering broken: {received}"
