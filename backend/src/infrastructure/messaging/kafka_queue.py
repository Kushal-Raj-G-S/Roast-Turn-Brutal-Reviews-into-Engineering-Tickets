"""
Kafka-based message queue implementation.

Slots into the same IMessageQueue port that InMemoryQueue and RedisQueue
already implement (see event_bus.py) — the pipeline and EventBus code
never change; only create_event_bus(backend="kafka") does.

Why Kafka here (and not just Redis):
    Review uploads arrive from multiple sources (bulk CSV, and platform
    connectors) at uneven rates, and the slow stage — ONNX embedding
    generation over the full batch — is the one most likely to crash or
    time out under load. Kafka gives durable, replayable log storage: if a
    consumer dies mid-batch the un-committed offsets are still on the
    broker, so processing resumes from the last commit instead of losing
    the batch (InMemoryQueue) or relying on Redis stream retention.

Delivery semantics — at-least-once, deliberately:
    Offsets are committed only after every handler for a batch succeeds
    (enable_auto_commit=False). A crash between handler-success and commit
    replays those messages, so handlers must be idempotent — which they
    are: the BigQuery loads delete-then-load per upload_id, and cluster
    persistence is keyed by cluster_id. Exactly-once would require
    transactional produce+consume across Postgres and BigQuery, which
    isn't worth the complexity when the sinks are already idempotent.

Failure handling:
    A handler exception retries the message up to max_retries with the
    retry counter carried in the envelope. Exhausted messages go to a
    dedicated dead-letter topic (<topic>.dlq) — NOT back onto the source
    topic, which would loop forever.

Works against any Kafka-protocol broker — a local Docker broker
(PLAINTEXT) or a managed one (Upstash, Redpanda, Confluent) over
SASL_SSL. Broker choice is config, never code.

Requires: pip install aiokafka
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .event_bus import IMessageQueue, Message

logger = logging.getLogger(__name__)

TOPIC_PREFIX = "roast.events."
DLQ_SUFFIX = ".dlq"


class KafkaQueue(IMessageQueue):
    """
    Kafka-backed implementation of IMessageQueue.

    One topic per event_type (e.g. "roast.events.UploadCompletedEvent"),
    one consumer group shared by all worker processes so replicas split
    partitions between them instead of each processing every message.
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        consumer_group: str = "roast-workers",
        security_protocol: str = "PLAINTEXT",
        sasl_mechanism: Optional[str] = None,
        sasl_username: Optional[str] = None,
        sasl_password: Optional[str] = None,
        max_batch_records: int = 100,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.consumer_group = consumer_group
        self.max_batch_records = max_batch_records
        self._auth_kwargs: Dict[str, Any] = {
            "security_protocol": security_protocol,
            **({"sasl_mechanism": sasl_mechanism} if sasl_mechanism else {}),
            **({"sasl_plain_username": sasl_username} if sasl_username else {}),
            **({"sasl_plain_password": sasl_password} if sasl_password else {}),
        }

        self._producer = None
        self._producer_lock = asyncio.Lock()
        self.handlers: Dict[str, List[Callable]] = {}
        self.is_consuming = False
        self._consumer_tasks: List[asyncio.Task] = []

    def _topic_for(self, event_type: str) -> str:
        return f"{TOPIC_PREFIX}{event_type}"

    def _dlq_for(self, event_type: str) -> str:
        return f"{self._topic_for(event_type)}{DLQ_SUFFIX}"

    async def _get_producer(self):
        """
        Lazy, race-safe producer init. Configured for durability over raw
        throughput: acks="all" waits for in-sync replicas, and the
        idempotent producer prevents duplicate writes on internal retry.
        """
        if self._producer is None:
            async with self._producer_lock:
                if self._producer is None:  # re-check inside the lock
                    from aiokafka import AIOKafkaProducer

                    producer = AIOKafkaProducer(
                        bootstrap_servers=self.bootstrap_servers,
                        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                        acks="all",
                        enable_idempotence=True,
                        compression_type="gzip",  # review text compresses well
                        linger_ms=20,             # small batching window
                        request_timeout_ms=30000,
                        **self._auth_kwargs,
                    )
                    await producer.start()
                    self._producer = producer
        return self._producer

    def _envelope(self, message: Message) -> Dict[str, Any]:
        return {
            "id": message.id,
            "event_type": message.event_type,
            "payload": message.payload,
            "timestamp": message.timestamp.isoformat(),
            "retry_count": message.retry_count,
            "max_retries": message.max_retries,
            "dead_letter": message.dead_letter,
        }

    async def publish(self, message: Message) -> None:
        """
        Publish to the event-type topic, keyed by message.id so all events
        for one entity land on the same partition and stay ordered
        relative to each other.
        """
        producer = await self._get_producer()
        topic = self._topic_for(message.event_type)

        await producer.send_and_wait(
            topic, value=self._envelope(message), key=message.id.encode("utf-8")
        )
        logger.debug(f"Published {message.id} -> {topic}")

    async def _publish_to_dlq(self, message: Message, error: str) -> None:
        """
        Route a permanently-failed message to its dead-letter topic with the
        failure reason attached. Separate topic (not the source topic) so
        poison messages can't loop.
        """
        producer = await self._get_producer()
        dlq_topic = self._dlq_for(message.event_type)

        envelope = self._envelope(message)
        envelope["dead_letter"] = True
        envelope["error"] = error
        envelope["failed_at"] = datetime.utcnow().isoformat()

        await producer.send_and_wait(
            dlq_topic, value=envelope, key=message.id.encode("utf-8")
        )
        logger.error(
            f"Message {message.id} exhausted {message.max_retries} retries -> {dlq_topic}: {error}"
        )

    async def subscribe(
        self,
        event_type: str,
        handler: Callable[[Message], Any],
    ) -> None:
        """Register a handler; the consumer is created in start_consuming()."""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
        logger.info(f"Registered Kafka handler for: {event_type}")

    async def start_consuming(self) -> None:
        """One consumer task per subscribed event type."""
        self.is_consuming = True

        for event_type in self.handlers:
            task = asyncio.create_task(self._consume_topic(event_type))
            self._consumer_tasks.append(task)

        logger.info(f"Started consuming {len(self._consumer_tasks)} Kafka topics")

    async def stop_consuming(self, grace_period: float = 15.0) -> None:
        """
        Graceful shutdown.

        Consumer tasks are NOT cancelled outright. Clearing is_consuming
        makes each loop exit after it finishes the batch it is holding, and
        we wait out a grace period for that to happen before force-
        cancelling stragglers.

        This ordering matters: cancelling mid-_dispatch aborts an in-flight
        retry-republish or dead-letter publish, and stopping the producer
        underneath it drops that message entirely — a message that failed
        permanently would vanish instead of landing on the DLQ. Caught by
        tests/integration/test_kafka_integration.py.
        """
        self.is_consuming = False

        if self._consumer_tasks:
            done, pending = await asyncio.wait(
                self._consumer_tasks, timeout=grace_period
            )
            if pending:
                logger.warning(
                    f"{len(pending)} Kafka consumer task(s) did not drain within "
                    f"{grace_period}s — force-cancelling"
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            self._consumer_tasks.clear()

        # Producer last: in-flight dispatch above may still need to publish
        # a retry or dead-letter record.
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

        logger.info("Stopped Kafka consumers")

    def _to_message(self, event_type: str, data: Dict[str, Any]) -> Message:
        return Message(
            id=data["id"],
            event_type=event_type,
            payload=data["payload"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            dead_letter=data.get("dead_letter", False),
        )

    async def _consume_topic(self, event_type: str):
        """
        Consume a topic. Offsets are committed once per successfully-drained
        batch rather than per record — per-record commits add a broker
        round-trip per message and cut throughput hard. A failure inside a
        batch is handled per-message (retry or DLQ) and the batch still
        commits afterwards, because every failed message has already been
        durably re-published elsewhere.
        """
        from aiokafka import AIOKafkaConsumer

        topic = self._topic_for(event_type)
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.consumer_group,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            max_poll_records=self.max_batch_records,
            # Embedding batches can take minutes; without a raised limit the
            # broker assumes the consumer died and rebalances mid-work.
            max_poll_interval_ms=600000,
            session_timeout_ms=60000,
            **self._auth_kwargs,
        )
        await consumer.start()

        handlers = self.handlers.get(event_type, [])

        try:
            while self.is_consuming:
                try:
                    batches = await consumer.getmany(
                        timeout_ms=1000, max_records=self.max_batch_records
                    )
                    if not batches:
                        continue

                    processed_any = False
                    for records in batches.values():
                        for record in records:
                            message = self._to_message(event_type, record.value)
                            await self._dispatch(message, handlers)
                            processed_any = True

                    if processed_any:
                        await consumer.commit()

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Kafka consumer loop error on {topic}: {e}", exc_info=True)
                    await asyncio.sleep(1)
        finally:
            await consumer.stop()

    async def _dispatch(self, message: Message, handlers: List[Callable]) -> None:
        """
        Run every handler for a message. On failure, retry via republish
        (with an incremented counter) or route to the DLQ once retries are
        exhausted. Never re-raises — a single poison message must not stall
        the whole partition.
        """
        try:
            for handler in handlers:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
        except Exception as e:
            if message.retry_count < message.max_retries:
                message.retry_count += 1
                logger.warning(
                    f"Handler failed for {message.id}, retry "
                    f"{message.retry_count}/{message.max_retries}: {e}"
                )
                await self.publish(message)
            else:
                await self._publish_to_dlq(message, str(e))

    async def ack(self, message: Message) -> None:
        """No-op: offsets are committed per drained batch in _consume_topic."""
        pass

    async def nack(self, message: Message, requeue: bool = True) -> None:
        """Explicit reject — requeue for retry, or send straight to the DLQ."""
        if requeue and message.retry_count < message.max_retries:
            message.retry_count += 1
            await self.publish(message)
        else:
            await self._publish_to_dlq(message, "explicitly nacked")
