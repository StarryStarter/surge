# app/api/reservations.py
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import get_reservation_service
from app.core.reservation.models import Reservation
from app.core.reservation.service import ReservationService

router = APIRouter(tags=["reservations"])


class ReserveRequest(BaseModel):
    requester_id: str = Field(min_length=1, max_length=200)


class ReservationResponse(BaseModel):
    id: UUID
    pool_id: UUID
    requester_id: str
    status: str


def _to_response(reservation: Reservation) -> ReservationResponse:
    return ReservationResponse(
        id=reservation.id,
        pool_id=reservation.pool_id,
        requester_id=reservation.requester_id,
        status=reservation.status.value,
    )


@router.post(
    "/pools/{pool_id}/reserve", response_model=ReservationResponse, status_code=201
)
async def reserve(
    pool_id: UUID,
    body: ReserveRequest,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationResponse:
    reservation = await service.reserve(pool_id, body.requester_id)
    return _to_response(reservation)


@router.post(
    "/reservations/{reservation_id}/confirm", response_model=ReservationResponse
)
async def confirm(
    reservation_id: UUID,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationResponse:
    reservation = await service.confirm(reservation_id)
    return _to_response(reservation)


@router.post(
    "/reservations/{reservation_id}/release", response_model=ReservationResponse
)
async def release(
    reservation_id: UUID,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationResponse:
    reservation = await service.release(reservation_id)
    return _to_response(reservation)