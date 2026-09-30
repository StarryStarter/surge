from typing import Annotated

import asyncpg
from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.admission.service import AdmissionService
from app.core.pool.repository import PoolRepository
from app.core.pool.service import PoolService
from app.core.reservation.repository import ReservationRepository
from app.core.reservation.service import ReservationService
from app.core.idempotency.service import IdempotencyService


def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_admission_service(request: Request) -> AdmissionService:
    return request.app.state.admission


def get_pool_service(
    db: Annotated[asyncpg.Pool, Depends(get_db_pool)],
    admission: Annotated[AdmissionService, Depends(get_admission_service)],
) -> PoolService:
    return PoolService(PoolRepository(db), admission)


def get_reservation_service(
    db: Annotated[asyncpg.Pool, Depends(get_db_pool)],
    admission: Annotated[AdmissionService, Depends(get_admission_service)],
) -> ReservationService:
    return ReservationService(ReservationRepository(db), admission)


def get_idempotency_service(
    redis: Annotated[Redis, Depends(get_redis)],
) -> IdempotencyService:
    return IdempotencyService(redis)