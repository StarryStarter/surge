-- app/db/schema.sql
-- Source of truth for the schema. No migration tool yet (not in the spec):
-- when this changes, recreate the dev/test databases.

CREATE TABLE IF NOT EXISTS resource_pools (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT        NOT NULL,
    capacity   INT         NOT NULL CHECK (capacity > 0),
    -- Phase 1-3 scaffolding only: the final design keeps the live counter in Redis.
    available  INT         NOT NULL CHECK (available >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reservations (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pool_id      UUID        NOT NULL REFERENCES resource_pools (id),
    requester_id TEXT        NOT NULL,
    status       TEXT        NOT NULL
                 CHECK (status IN ('HELD', 'CONFIRMED', 'RELEASED', 'EXPIRED')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS outbox_events (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type      TEXT        NOT NULL,
    pool_id         UUID        NOT NULL REFERENCES resource_pools (id),
    status          TEXT        NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'DONE', 'FAILED')),
    attempts        INT         NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS outbox_events_due_idx
    ON outbox_events (next_attempt_at)
    WHERE status = 'PENDING';

ALTER TABLE reservations ADD COLUMN IF NOT EXISTS hold_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS reservations_hold_expiry_idx
    ON reservations (hold_expires_at) WHERE status = 'HELD';
CREATE INDEX IF NOT EXISTS reservations_pool_status_idx
    ON reservations (pool_id, status);
CREATE INDEX IF NOT EXISTS outbox_events_pool_status_idx
    ON outbox_events (pool_id, status);