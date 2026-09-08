"""
Smoke tests for KafkaQueue — verify it satisfies the IMessageQueue port
and that topic-naming/envelope logic is correct, without needing a real
Kafka broker (no network calls in CI).
"""

import pytest

from src.infrastructure.messaging.event_bus import IMessageQueue, Message
from src.infrastructure.messaging.kafka_queue import TOPIC_PREFIX, KafkaQueue


def test_kafka_queue_implements_message_queue_port():
    queue = KafkaQueue(bootstrap_servers="localhost:9092")
    assert isinstance(queue, IMessageQueue)


def test_topic_naming_matches_event_type():
    queue = KafkaQueue()
    assert queue._topic_for("UploadCompletedEvent") == f"{TOPIC_PREFIX}UploadCompletedEvent"


def test_hosted_broker_auth_kwargs_built_correctly():
    """Config for a managed broker (Upstash/Confluent) over SASL_SSL —
    no local Kafka install required, just credentials."""
    queue = KafkaQueue(
        bootstrap_servers="my-broker.upstash.io:9092",
        security_protocol="SASL_SSL",
        sasl_mechanism="SCRAM-SHA-256",
        sasl_username="user",
        sasl_password="pass",
    )
    assert queue._auth_kwargs["security_protocol"] == "SASL_SSL"
    assert queue._auth_kwargs["sasl_mechanism"] == "SCRAM-SHA-256"
    assert queue._auth_kwargs["sasl_plain_username"] == "user"


@pytest.mark.asyncio
async def test_subscribe_registers_handler():
    queue = KafkaQueue()

    async def handler(message: Message):
        pass

    await queue.subscribe("UploadCompletedEvent", handler)
    assert "UploadCompletedEvent" in queue.handlers
    assert handler in queue.handlers["UploadCompletedEvent"]
