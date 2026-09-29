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

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key          TEXT PRIMARY KEY,
    requester_id TEXT,
    response     JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);