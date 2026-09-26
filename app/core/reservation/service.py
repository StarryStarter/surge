# app/core/reservation/service.py
from uuid import UUID

import asyncpg

from app.core.errors import (
    InvalidTransition,
    PoolNotFound,
    PoolSoldOut,
    ReservationNotFound,
)
from app.core.pool.repository import PoolRepository
from app.core.reservation.models import Reservation, ReservationStatus, can_transition
from app.core.reservation.repository import ReservationRepository


class ReservationService:
    def __init__(
        self,
        db: asyncpg.Pool,
        pools: PoolRepository,
        reservations: ReservationRepository,
    ) -> None:
        self._db = db
        self._pools = pools
        self._reservations = reservations

    async def reserve(self, pool_id: UUID, requester_id: str) -> Reservation:
        # One connection, one transaction: the lock, the check, the decrement,
        # and the reservation write all happen as a single uninterruptible unit.
        async with self._db.acquire() as conn:
            async with conn.transaction():
                pool = await self._pools.get_for_update(conn, pool_id)
                if pool is None:
                    raise PoolNotFound(f"pool {pool_id} not found")
                if pool.available <= 0:
                    raise PoolSoldOut(f"pool {pool_id} is sold out")

                await self._pools.decrement(conn, pool_id)
                return await self._reservations.create_held(pool_id, requester_id, conn)

    async def confirm(self, reservation_id: UUID) -> Reservation:
        return await self._transition(
            reservation_id, ReservationStatus.HELD, ReservationStatus.CONFIRMED
        )

    async def release(self, reservation_id: UUID) -> Reservation:
        released = await self._transition(
            reservation_id, ReservationStatus.HELD, ReservationStatus.RELEASED
        )
        pool = await self._pools.get(released.pool_id)
        if pool is not None:
            await self._pools.set_available(pool.id, pool.available + 1)
        return released

    async def _transition(
        self,
        reservation_id: UUID,
        from_status: ReservationStatus,
        to_status: ReservationStatus,
    ) -> Reservation:
        if not can_transition(from_status, to_status):
            current = await self._reservations.get(reservation_id)
            if current is None:
                raise ReservationNotFound(f"reservation {reservation_id} not found")
            raise InvalidTransition(
                f"cannot move reservation from {current.status} to {to_status}"
            )

        updated = await self._reservations.transition(
            reservation_id, from_status, to_status
        )
        if updated is not None:
            return updated

        current = await self._reservations.get(reservation_id)
        if current is None:
            raise ReservationNotFound(f"reservation {reservation_id} not found")
        raise InvalidTransition(
            f"cannot move reservation from {current.status} to {to_status}"
        )