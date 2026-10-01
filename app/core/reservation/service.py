import logging
from functools import partial
from typing import NoReturn
from uuid import UUID

from app.core.admission.service import AdmissionService
from app.core.errors import InvalidTransition, ReservationNotFound
from app.core.outbox.handlers import handle_event
from app.core.outbox.repository import OutboxRepository
from app.core.reservation.models import Reservation, ReservationStatus, can_transition
from app.core.reservation.repository import ReservationRepository

logger = logging.getLogger(__name__)

class ReservationService:
    def __init__(
        self,
        reservations: ReservationRepository,
        admission: AdmissionService,
        outbox: OutboxRepository,
    ) -> None:
        self._reservations = reservations
        self._admission = admission
        self._outbox = outbox

    async def reserve(self, pool_id: UUID, requester_id: str) -> Reservation:
        # 1) The fast, atomic yes/no decision: Redis only, no database, no lock.
        await self._admission.admit(pool_id)
        # 2) The permanent record. If it fails, Redis has already given the unit
        #    away, so hand it back before surfacing the error. BaseException (not
        #    Exception) so a client disconnect that cancels the request between
        #    the two steps doesn't leak the unit either.
        try:
            return await self._reservations.create_held(pool_id, requester_id)
        except BaseException:
            try:
                await self._admission.release(pool_id)
            except Exception:
                # Both stores failed. The original error still reaches the caller;
                # the drift is left for the reconciler (Phase 11) to repair.
                logger.exception(
                    "could not return unit for pool %s after failed reservation "
                    "write; counter is now low until reconciled",
                    pool_id,
                )
            raise

    async def confirm(self, reservation_id: UUID) -> Reservation:
        return await self._transition(
            reservation_id, ReservationStatus.HELD, ReservationStatus.CONFIRMED
        )

    async def release(self, reservation_id: UUID) -> Reservation:
        # The status change and the "return one unit" event commit together.
        result = await self._reservations.release_and_enqueue(reservation_id)
        if result is None:
            await self._explain_failed_transition(
                reservation_id, ReservationStatus.RELEASED
            )
        released, event_id = result
        await self._deliver_now(event_id)
        return released

    async def _deliver_now(self, event_id: UUID) -> None:
        """Fast path: try to give the unit back right away. If anything goes
        wrong the event stays PENDING and the background worker retries it, so
        the release has still succeeded from the caller's point of view."""
        try:
            await self._outbox.process_batch(
                partial(handle_event, self._admission), limit=1, only_id=event_id
            )
        except Exception:
            logger.warning(
                "inline delivery of outbox event %s failed; worker will retry",
                event_id,
                exc_info=True,
            )

    async def _transition(
        self,
        reservation_id: UUID,
        from_status: ReservationStatus,
        to_status: ReservationStatus,
    ) -> Reservation:
        if not can_transition(from_status, to_status):
            await self._explain_failed_transition(reservation_id, to_status)

        updated = await self._reservations.transition(
            reservation_id, from_status, to_status
        )
        if updated is not None:
            return updated

        await self._explain_failed_transition(reservation_id, to_status)

    async def _explain_failed_transition(
        self, reservation_id: UUID, to_status: ReservationStatus
    ) -> NoReturn:
        current = await self._reservations.get(reservation_id)
        if current is None:
            raise ReservationNotFound(f"reservation {reservation_id} not found")
        raise InvalidTransition(
            f"cannot move reservation from {current.status} to {to_status}"
        )