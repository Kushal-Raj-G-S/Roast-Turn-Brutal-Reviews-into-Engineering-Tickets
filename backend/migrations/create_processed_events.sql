-- Inbox table for idempotent event consumption.
--
-- Why this is required, not optional: KafkaQueue delivers at-least-once
-- (offsets commit only after handlers succeed, so a crash in that window
-- replays the batch). Without dedup, a replay re-sends a user's
-- Discord/push/email alert — the most visible possible form of the bug,
-- since the user personally receives the duplicate.
--
-- The consumer claims an event by inserting a row here first. The
-- composite primary key makes the claim atomic: a replayed event hits a
-- conflict and is skipped instead of re-notifying.
--
-- The key is (event_id, consumer_name), NOT event_id alone: several
-- independent consumers may each need to handle the same event exactly
-- once, and a single-column key would let whichever consumer claimed it
-- first starve all the others.

CREATE TABLE IF NOT EXISTS processed_events (
    -- DomainEvent.event_id (a UUID string generated at publish time)
    event_id      TEXT        NOT NULL,
    consumer_name TEXT        NOT NULL,
    event_type    TEXT        NOT NULL,
    upload_id     BIGINT      NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (event_id, consumer_name)
);

-- Supports the retention sweep below.
CREATE INDEX IF NOT EXISTS processed_events_processed_at_idx
    ON processed_events (processed_at);

-- Retention: this table only needs to cover the window in which a replay
-- is possible (i.e. Kafka topic retention). Kept as a documented manual /
-- cron step rather than a trigger, so it stays visible:
--
--   DELETE FROM processed_events WHERE processed_at < now() - interval '30 days';
