"""
Integration tests for the event-consumer inbox against a REAL Postgres.

This is the test that matters most for correctness of the whole event
path. KafkaQueue is at-least-once by design, so a redelivery of an
UPLOAD_COMPLETED event WILL happen (crash between handler success and
offset commit, or a consumer-group rebalance). Without the inbox claim,
that redelivery re-sends the user's Discord/push/email alert — a bug the
user personally receives.

`ON CONFLICT DO NOTHING` + rowcount is the mechanism, and its behaviour is
Postgres-specific, so it has to be tested on Postgres rather than mocked.
It also has to be tested on a THROWAWAY database — the production
DATABASE_URL points at real user data, which is why _claim_event takes an
injectable session_factory.

Run with:

    docker run -d --name roast-pg-test -p 55432:5432 \
      -e POSTGRES_PASSWORD=test -e POSTGRES_USER=test -e POSTGRES_DB=roast_test \
      postgres:16-alpine

    pytest tests/integration/test_consumer_idempotency.py -v
"""

import os
import pathlib
import socket
import uuid

import pytest

pytestmark = pytest.mark.integration

PG_DSN = os.getenv(
    "TEST_POSTGRES_DSN",
    "postgresql+psycopg2://test:test@localhost:55432/roast_test",
)
PG_HOST_PORT = ("localhost", 55432)


def _reachable() -> bool:
    try:
        with socket.create_connection(PG_HOST_PORT, timeout=3):
            return True
    except OSError:
        return False


pytest.importorskip("sqlalchemy")

if not _reachable():
    pytest.skip(
        f"No throwaway Postgres at {PG_HOST_PORT[0]}:{PG_HOST_PORT[1]}",
        allow_module_level=True,
    )

from src.infrastructure.messaging.consumers import (  # noqa: E402
    NOTIFICATION_CONSUMER,
    _claim_event,
)

MIGRATION = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations"
    / "create_processed_events.sql"
)


@pytest.fixture(scope="module")
def session_factory():
    """
    Applies the real migration file to a throwaway database — so this also
    verifies migrations/create_processed_events.sql is valid SQL that
    Postgres actually accepts, not just plausible-looking DDL.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(PG_DSN, future=True)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS processed_events"))
        conn.execute(text(MIGRATION.read_text(encoding="utf-8")))

    return sessionmaker(bind=engine, future=True)


def _count(session_factory, event_id: str) -> int:
    from sqlalchemy import text

    with session_factory() as s:
        return s.execute(
            text("SELECT count(*) FROM processed_events WHERE event_id = :e"),
            {"e": event_id},
        ).scalar()


def test_migration_creates_expected_schema(session_factory):
    from sqlalchemy import text

    with session_factory() as s:
        cols = dict(
            s.execute(
                text(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'processed_events'
                    """
                )
            ).all()
        )

    assert set(cols) == {
        "event_id",
        "consumer_name",
        "event_type",
        "upload_id",
        "processed_at",
    }, cols
    assert cols["upload_id"] == "bigint"
    assert cols["processed_at"].startswith("timestamp with")


def test_first_claim_wins(session_factory):
    event_id = str(uuid.uuid4())
    assert _claim_event(
        event_id, NOTIFICATION_CONSUMER, "upload.completed", 42,
        session_factory=session_factory,
    ) is True
    assert _count(session_factory, event_id) == 1


def test_redelivery_is_rejected(session_factory):
    """The core guarantee: a replayed event must NOT be processed twice."""
    event_id = str(uuid.uuid4())

    first = _claim_event(
        event_id, NOTIFICATION_CONSUMER, "upload.completed", 42,
        session_factory=session_factory,
    )
    second = _claim_event(
        event_id, NOTIFICATION_CONSUMER, "upload.completed", 42,
        session_factory=session_factory,
    )
    third = _claim_event(
        event_id, NOTIFICATION_CONSUMER, "upload.completed", 42,
        session_factory=session_factory,
    )

    assert first is True
    assert second is False
    assert third is False
    # And the conflict didn't insert duplicate rows.
    assert _count(session_factory, event_id) == 1


def test_different_consumers_each_get_one_claim(session_factory):
    """
    A second, independent consumer of the same event must still get its
    own claim — this is why the key is (event_id, consumer_name) rather
    than event_id alone.
    """
    event_id = str(uuid.uuid4())

    assert _claim_event(
        event_id, "upload_notifications", "upload.completed", 7,
        session_factory=session_factory,
    ) is True
    assert _claim_event(
        event_id, "warehouse_sync", "upload.completed", 7,
        session_factory=session_factory,
    ) is True
    # But neither can claim twice.
    assert _claim_event(
        event_id, "warehouse_sync", "upload.completed", 7,
        session_factory=session_factory,
    ) is False

    assert _count(session_factory, event_id) == 2


def test_null_upload_id_is_allowed(session_factory):
    """UPLOAD_FAILED events may carry no upload_id."""
    event_id = str(uuid.uuid4())
    assert _claim_event(
        event_id, NOTIFICATION_CONSUMER, "upload.failed", None,
        session_factory=session_factory,
    ) is True
    assert _count(session_factory, event_id) == 1


def test_distinct_events_do_not_interfere(session_factory):
    ids = [str(uuid.uuid4()) for _ in range(5)]
    for e in ids:
        assert _claim_event(
            e, NOTIFICATION_CONSUMER, "upload.completed", 1,
            session_factory=session_factory,
        ) is True
    for e in ids:
        assert _count(session_factory, e) == 1


def test_concurrent_claims_only_one_wins(session_factory):
    """
    Two consumer replicas can receive the same event simultaneously after a
    rebalance. Only one may win, and the loser must not error — the claim
    has to be atomic at the database level, not a read-then-write race.
    """
    from concurrent.futures import ThreadPoolExecutor

    event_id = str(uuid.uuid4())

    def claim():
        return _claim_event(
            event_id, NOTIFICATION_CONSUMER, "upload.completed", 99,
            session_factory=session_factory,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: claim(), range(8)))

    assert sum(results) == 1, f"expected exactly one winner, got {results}"
    assert _count(session_factory, event_id) == 1
