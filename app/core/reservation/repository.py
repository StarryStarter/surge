from uuid import UUID

import asyncpg

from app.core.outbox.models import UNIT_RETURNED
from app.core.reservation.models import Reservation, ReservationStatus

_COLUMNS = "id, pool_id, requester_id, status, created_at"

def _to_reservation(row: asyncpg.Record) -> Reservation:
    return Reservation(**{**row, "status": ReservationStatus(row["status"])})

class ReservationRepository:
    def __init__(self, db: asyncpg.Pool, hold_ttl_seconds: int = 900) -> None:
        self._db = db
        self._hold_ttl_seconds = hold_ttl_seconds

    async def create_held(self, pool_id: UUID, requester_id: str) -> Reservation:
        row = await self._db.fetchrow(
            f"INSERT INTO reservations "
            f"(pool_id, requester_id, status, hold_expires_at) "
            f"VALUES ($1, $2, 'HELD', now() + make_interval(secs => $3)) "
            f"RETURNING {_COLUMNS}",
            pool_id,
            requester_id,
            float(self._hold_ttl_seconds),
        )
        return _to_reservation(row)

    async def get(self, reservation_id: UUID) -> Reservation | None:
        row = await self._db.fetchrow(
            f"SELECT {_COLUMNS} FROM reservations WHERE id = $1", reservation_id
        )
        return _to_reservation(row) if row else None

    async def transition(
        self,
        reservation_id: UUID,
        from_status: ReservationStatus,
        to_status: ReservationStatus,
    ) -> Reservation | None:
        """Change status only if it's currently `from_status` — check and
        change in one atomic UPDATE. Returns None if no row matched."""
        row = await self._db.fetchrow(
            f"UPDATE reservations SET status = $3, updated_at = now() "
            f"WHERE id = $1 AND status = $2 RETURNING {_COLUMNS}",
            reservation_id,
            from_status.value,
            to_status.value,
        )
        return _to_reservation(row) if row else None

    async def release_and_enqueue(
        self, reservation_id: UUID
    ) -> tuple[Reservation, UUID] | None:
        """HELD -> RELEASED and the 'return one unit' outbox event, committed
        together: both happen or neither does. Returns None if the reservation
        wasn't HELD (or doesn't exist)."""
        async with self._db.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                f"UPDATE reservations SET status = 'RELEASED', updated_at = now() "
                f"WHERE id = $1 AND status = 'HELD' RETURNING {_COLUMNS}",
                reservation_id,
            )
            if row is None:
                return None
            reservation = _to_reservation(row)
            event_id = await conn.fetchval(
                "INSERT INTO outbox_events (event_type, pool_id) "
                "VALUES ($1, $2) RETURNING id",
                UNIT_RETURNED,
                reservation.pool_id,
            )
            return reservation, event_id

    async def expire_due_holds(self, limit: int) -> int:
        """HELD past its deadline -> EXPIRED, each with a 'return one unit'
        event, all in one transaction. A confirm racing with this either wins
        first (row is CONFIRMED, not touched here) or loses (it gets a 409)."""
        async with self._db.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                "UPDATE reservations SET status = 'EXPIRED', updated_at = now() "
                "WHERE id IN ("
                "  SELECT id FROM reservations "
                "  WHERE status = 'HELD' AND hold_expires_at <= now() "
                "  ORDER BY hold_expires_at LIMIT $1 FOR UPDATE SKIP LOCKED"
                ") RETURNING pool_id",
                limit,
            )
            if rows:
                await conn.executemany(
                    "INSERT INTO outbox_events (event_type, pool_id) VALUES ($1, $2)",
                    [(UNIT_RETURNED, row["pool_id"]) for row in rows],
                )
            return len(rows)