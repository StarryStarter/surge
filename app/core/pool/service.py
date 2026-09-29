from dataclasses import replace
from uuid import UUID

from app.core.admission.service import AdmissionService
from app.core.errors import PoolNotFound
from app.core.pool.models import Pool
from app.core.pool.repository import PoolRepository


class PoolService:
    def __init__(self, pools: PoolRepository, admission: AdmissionService) -> None:
        self._pools = pools
        self._admission = admission

    async def create_pool(self, name: str, capacity: int) -> Pool:
        pool = await self._pools.create(name, capacity)
        await self._admission.open_pool(pool.id, capacity)
        return pool

    async def get_pool(self, pool_id: UUID) -> Pool:
        pool = await self._pools.get(pool_id)
        if pool is None:
            raise PoolNotFound(f"pool {pool_id} not found")
        # Redis holds the live count; the Postgres `available` column is now stale.
        return replace(pool, available=await self._admission.available(pool_id))