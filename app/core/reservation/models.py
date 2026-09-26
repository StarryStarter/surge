# app/core/reservation/models.py
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ReservationStatus(StrEnum):
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


# CONFIRMED/RELEASED/EXPIRED are terminal — nothing leaves them, not even
# back to themselves. Pure function, no DB/FastAPI, so it's cheaply unit tested.
_ALLOWED: dict[ReservationStatus, frozenset[ReservationStatus]] = {
    ReservationStatus.HELD: frozenset(
        {ReservationStatus.CONFIRMED, ReservationStatus.RELEASED, ReservationStatus.EXPIRED}
    ),
    ReservationStatus.CONFIRMED: frozenset(),
    ReservationStatus.RELEASED: frozenset(),
    ReservationStatus.EXPIRED: frozenset(),
}


def can_transition(from_status: ReservationStatus, to_status: ReservationStatus) -> bool:
    return to_status in _ALLOWED[from_status]


@dataclass(frozen=True, slots=True)
class Reservation:
    id: UUID
    pool_id: UUID
    requester_id: str
    status: ReservationStatus
    created_at: datetime