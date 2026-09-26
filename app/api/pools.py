# app/api/pools.py
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import get_pool_service
from app.core.pool.models import Pool
from app.core.pool.service import PoolService

router = APIRouter(prefix="/pools", tags=["pools"])


class CreatePoolRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    capacity: int = Field(gt=0)


class PoolResponse(BaseModel):
    id: UUID
    name: str
    capacity: int
    available: int


def _to_response(pool: Pool) -> PoolResponse:
    return PoolResponse(
        id=pool.id, name=pool.name, capacity=pool.capacity, available=pool.available
    )


@router.post("", response_model=PoolResponse, status_code=201)
async def create_pool(
    body: CreatePoolRequest,
    service: Annotated[PoolService, Depends(get_pool_service)],
) -> PoolResponse:
    pool = await service.create_pool(body.name, body.capacity)
    return _to_response(pool)


@router.get("/{pool_id}/availability", response_model=PoolResponse)
async def get_availability(
    pool_id: UUID,
    service: Annotated[PoolService, Depends(get_pool_service)],
) -> PoolResponse:
    pool = await service.get_pool(pool_id)
    return _to_response(pool)