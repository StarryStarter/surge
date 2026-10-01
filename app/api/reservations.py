from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_idempotency_service, get_reservation_service
from app.core.idempotency.service import IdempotencyService
from app.core.reservation.models import Reservation
from app.core.reservation.service import ReservationService
from app.core.fairness.rate_limiter import RateLimiter
from app.observability.metrics import RATE_LIMITED
from app.api.dependencies import (
    get_idempotency_service,
    get_rate_limiter,
    get_reservation_service,
)

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
    idempotency: Annotated[IdempotencyService, Depends(get_idempotency_service)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ReservationResponse:
    # A replay of a finished request is free: it doesn't count against the limit.
    cached = await idempotency.get_cached_response(idempotency_key)
    if cached is not None:
        return ReservationResponse(**cached)

    retry_after = await limiter.hit(f"reserve:{body.requester_id}")
    if retry_after is not None:
        RATE_LIMITED.inc()
        raise HTTPException(
            429,
            "too many requests, slow down",
            headers={"Retry-After": str(retry_after)},
        )

    if not await idempotency.try_claim(idempotency_key):
        raise HTTPException(409, "duplicate request already in progress, retry shortly")

    try:
        reservation = await service.reserve(pool_id, body.requester_id)
    except Exception:
        await idempotency.release_claim(idempotency_key)
        raise

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
    idempotency: Annotated[IdempotencyService, Depends(get_idempotency_service)],
) -> ReservationResponse:
    cached = await idempotency.get_cached_response(idempotency_key)
    if cached is not None:
        return ReservationResponse(**cached)

    if not await idempotency.try_claim(idempotency_key):
        raise HTTPException(409, "duplicate request already in progress, retry shortly")

    try:
        reservation = await service.confirm(reservation_id)
    except Exception:
        await idempotency.release_claim(idempotency_key)
        raise

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