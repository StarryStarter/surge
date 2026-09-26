# app/core/pool/service.py
from uuid import UUID

from app.core.errors import PoolNotFound
from app.core.pool.models import Pool
from app.core.pool.repository import PoolRepository


class PoolService:
    def __init__(self, pools: PoolRepository) -> None:
        self._pools = pools

    async def create_pool(self, name: str, capacity: int) -> Pool:
        return await self._pools.create(name, capacity)

    async def get_pool(self, pool_id: UUID) -> Pool:
        pool = await self._pools.get(pool_id)
        if pool is None:
            raise PoolNotFound(f"pool {pool_id} not found")
        return pool