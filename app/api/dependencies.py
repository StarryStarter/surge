# app/api/dependencies.py
from typing import Annotated

import asyncpg
from fastapi import Depends, Request

from app.core.pool.repository import PoolRepository
from app.core.pool.service import PoolService
from app.core.reservation.repository import ReservationRepository
from app.core.reservation.service import ReservationService


def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


def get_pool_service(db: Annotated[asyncpg.Pool, Depends(get_db_pool)]) -> PoolService:
    return PoolService(PoolRepository(db))


def get_reservation_service(
    db: Annotated[asyncpg.Pool, Depends(get_db_pool)],
) -> ReservationService:
    return ReservationService(db, PoolRepository(db), ReservationRepository(db))