from dataclasses import dataclass
from uuid import UUID

import asyncpg

@dataclass(frozen=True, slots=True)
class PoolSnapshot:
    pool_id: UUID
    capacity: int
    active: int   # HELD + CONFIRMED reservations
    pending: int  # returns not yet applied to Redis (PENDING or FAILED events)

class ReconciliationRepository:
    def __init__(self, db: asyncpg.Pool) -> None:
        self._db = db

    async def snapshot(self) -> list[PoolSnapshot]:
        """One statement, so Postgres gives us a consistent view of all pools."""
        rows = await self._db.fetch(
            """
            SELECT p.id AS pool_id, p.capacity,
                   COALESCE(r.active, 0) AS active,
                   COALESCE(o.pending, 0) AS pending
            FROM resource_pools p
            LEFT JOIN (
                SELECT pool_id, count(*) AS active FROM reservations
                WHERE status IN ('HELD', 'CONFIRMED') GROUP BY pool_id
            ) r ON r.pool_id = p.id
            LEFT JOIN (
                SELECT pool_id, count(*) AS pending FROM outbox_events
                WHERE event_type = 'UNIT_RETURNED'
                  AND status IN ('PENDING', 'FAILED') GROUP BY pool_id
            ) o ON o.pool_id = p.id
            """
        )
        return [PoolSnapshot(**row) for row in rows]