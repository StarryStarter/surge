from uuid import UUID

from app.core.admission.service import AdmissionService
from app.core.errors import InvalidTransition, ReservationNotFound
from app.core.reservation.models import Reservation, ReservationStatus, can_transition
from app.core.reservation.repository import ReservationRepository


class ReservationService:
    def __init__(
        self, reservations: ReservationRepository, admission: AdmissionService
    ) -> None:
        self._reservations = reservations
        self._admission = admission

    async def reserve(self, pool_id: UUID, requester_id: str) -> Reservation:
        # 1) The fast, atomic yes/no decision: Redis only, no database, no lock.
        await self._admission.admit(pool_id)
        # 2) The permanent record. Known gap: if this insert fails, one unit stays
        #    taken in Redis with no record in Postgres. That errs toward selling
        #    too few, never too many. The outbox pattern (Phase 9) closes it.
        return await self._reservations.create_held(pool_id, requester_id)

    async def confirm(self, reservation_id: UUID) -> Reservation:
        return await self._transition(
            reservation_id, ReservationStatus.HELD, ReservationStatus.CONFIRMED
        )

    async def release(self, reservation_id: UUID) -> Reservation:
        released = await self._transition(
            reservation_id, ReservationStatus.HELD, ReservationStatus.RELEASED
        )
        await self._admission.release(released.pool_id)
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