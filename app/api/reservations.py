from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_idempotency_repo, get_reservation_service
from app.core.idempotency.repository import IdempotencyRepository
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
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    service: Annotated[ReservationService, Depends(get_reservation_service)],
    idempotency: Annotated[IdempotencyRepository, Depends(get_idempotency_repo)],
) -> ReservationResponse:
    cached = await idempotency.get_response(idempotency_key)
    if cached is not None:
        return ReservationResponse(**cached)

    if not await idempotency.try_claim(idempotency_key, body.requester_id):
        # Known gap: a true simultaneous duplicate is told to retry shortly,
        # rather than being made to wait for the first attempt's result.
        raise HTTPException(409, "duplicate request already in progress, retry shortly")

    reservation = await service.reserve(pool_id, body.requester_id)
    response = _to_response(reservation)
    await idempotency.save_response(idempotency_key, response.model_dump(mode="json"))
    return response


@router.post(
    "/reservations/{reservation_id}/confirm", response_model=ReservationResponse
)
async def confirm(
    reservation_id: UUID,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    service: Annotated[ReservationService, Depends(get_reservation_service)],
    idempotency: Annotated[IdempotencyRepository, Depends(get_idempotency_repo)],
) -> ReservationResponse:
    cached = await idempotency.get_response(idempotency_key)
    if cached is not None:
        return ReservationResponse(**cached)

    if not await idempotency.try_claim(idempotency_key, None):
        raise HTTPException(409, "duplicate request already in progress, retry shortly")

    reservation = await service.confirm(reservation_id)
    response = _to_response(reservation)
    await idempotency.save_response(idempotency_key, response.model_dump(mode="json"))
    return response


@router.post(
    "/reservations/{reservation_id}/release", response_model=ReservationResponse
)
async def release(
    reservation_id: UUID,
    service: Annotated[ReservationService, Depends(get_reservation_service)],
) -> ReservationResponse:
    reservation = await service.release(reservation_id)
    return _to_response(reservation)