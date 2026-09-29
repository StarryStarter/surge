from uuid import UUID

import asyncpg

from app.core.reservation.models import Reservation, ReservationStatus

_COLUMNS = "id, pool_id, requester_id, status, created_at"


def _to_reservation(row: asyncpg.Record) -> Reservation:
    return Reservation(**{**row, "status": ReservationStatus(row["status"])})


class ReservationRepository:
    def __init__(self, db: asyncpg.Pool) -> None:
        self._db = db

    async def create_held(self, pool_id: UUID, requester_id: str) -> Reservation:
        row = await self._db.fetchrow(
            f"INSERT INTO reservations (pool_id, requester_id, status) "
            f"VALUES ($1, $2, 'HELD') RETURNING {_COLUMNS}",
            pool_id,
            requester_id,
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