from typing import Annotated

import asyncpg
from app.core.outbox.repository import OutboxRepository
from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.admission.service import AdmissionService
from app.core.pool.repository import PoolRepository
from app.core.pool.service import PoolService
from app.core.reservation.repository import ReservationRepository
from app.core.reservation.service import ReservationService
from app.core.idempotency.service import IdempotencyService
from app.config import Settings, get_settings
from app.core.outbox.repository import OutboxRepository
from app.core.fairness.rate_limiter import RateLimiter

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


def get_outbox_repo(
    db: Annotated[asyncpg.Pool, Depends(get_db_pool)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OutboxRepository:
    return OutboxRepository(db, settings.outbox_max_attempts)

def get_reservation_service(
    db: Annotated[asyncpg.Pool, Depends(get_db_pool)],
    admission: Annotated[AdmissionService, Depends(get_admission_service)],
    outbox: Annotated[OutboxRepository, Depends(get_outbox_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReservationService:
    return ReservationService(
        ReservationRepository(db, settings.hold_ttl_seconds), admission, outbox
    )

def get_idempotency_service(
    redis: Annotated[Redis, Depends(get_redis)],
) -> IdempotencyService:
    return IdempotencyService(redis)

def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter