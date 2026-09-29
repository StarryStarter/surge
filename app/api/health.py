# app/api/health.py
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.api.dependencies import get_db_pool
from app.config import Settings, get_settings

from redis.asyncio import Redis

from app.api.dependencies import get_db_pool, get_redis

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/healthz", response_model=HealthResponse)
async def healthz(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=__version__)


@router.get("/readyz", response_model=HealthResponse)
async def readyz(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[asyncpg.Pool, Depends(get_db_pool)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> HealthResponse:
    await db.fetchval("SELECT 1")
    await redis.ping()
    return HealthResponse(status="ready", service=settings.app_name, version=__version__)