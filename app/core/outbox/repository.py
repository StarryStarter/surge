import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

import asyncpg

from app.core.outbox.models import FailedOutboxEvent, OutboxEvent
from app.observability.metrics import OUTBOX_EVENTS

logger = logging.getLogger(__name__)

_MAX_BACKOFF_SECONDS = 60

class OutboxRepository:
    def __init__(self, db: asyncpg.Pool, max_attempts: int = 8) -> None:
        self._db = db
        self._max_attempts = max_attempts

    async def process_batch(
        self,
        handler: Callable[[OutboxEvent], Awaitable[None]],
        limit: int,
        only_id: UUID | None = None,
    ) -> int:
        """Claim due PENDING events, run `handler` on each, record the result.

        SKIP LOCKED lets several workers (and the inline fast path) run at once
        without double-claiming rows. A failing handler never raises out of
        here: the event is rescheduled with exponential backoff, and after
        `max_attempts` failures it moves to FAILED (the dead-letter queue).
        Returns how many events were claimed.
        """
        async with self._db.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                "SELECT id, event_type, pool_id, attempts FROM outbox_events "
                "WHERE status = 'PENDING' AND next_attempt_at <= now() "
                "AND ($2::uuid IS NULL OR id = $2) "
                "ORDER BY created_at LIMIT $1 FOR UPDATE SKIP LOCKED",
                limit,
                only_id,
            )
            for row in rows:
                event = OutboxEvent(**row)
                try:
                    await handler(event)
                except Exception as exc:
                    attempts = event.attempts + 1
                    error = repr(exc)[:500]
                    if attempts >= self._max_attempts:
                        await conn.execute(
                            "UPDATE outbox_events SET status = 'FAILED', "
                            "attempts = $2, last_error = $3, processed_at = now() "
                            "WHERE id = $1",
                            event.id,
                            attempts,
                            error,
                        )
                        OUTBOX_EVENTS.labels("dead_lettered").inc()
                        logger.error(
                            "outbox event %s moved to the dead-letter queue "
                            "after %d attempts: %s",
                            event.id,
                            attempts,
                            error,
                        )
                    else:
                        delay = float(min(2**attempts, _MAX_BACKOFF_SECONDS))
                        await conn.execute(
                            "UPDATE outbox_events SET attempts = $2, "
                            "last_error = $3, "
                            "next_attempt_at = now() + make_interval(secs => $4) "
                            "WHERE id = $1",
                            event.id,
                            attempts,
                            error,
                            delay,
                        )
                        OUTBOX_EVENTS.labels("retried").inc()
                else:
                    await conn.execute(
                        "UPDATE outbox_events SET status = 'DONE', "
                        "processed_at = now() WHERE id = $1",
                        event.id,
                    )
                    OUTBOX_EVENTS.labels("delivered").inc()
            return len(rows)

    async def list_failed(self, limit: int = 100) -> list[FailedOutboxEvent]:
        rows = await self._db.fetch(
            "SELECT id, event_type, pool_id, attempts, last_error, created_at "
            "FROM outbox_events WHERE status = 'FAILED' "
            "ORDER BY created_at LIMIT $1",
            limit,
        )
        return [FailedOutboxEvent(**row) for row in rows]

    async def requeue(self, event_id: UUID) -> bool:
        """Put a dead-lettered event back in line. False if it wasn't FAILED."""
        result = await self._db.execute(
            "UPDATE outbox_events SET status = 'PENDING', attempts = 0, "
            "next_attempt_at = now(), processed_at = NULL "
            "WHERE id = $1 AND status = 'FAILED'",
            event_id,
        )
        return result == "UPDATE 1"