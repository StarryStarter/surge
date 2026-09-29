from uuid import UUID

import asyncpg

from app.core.pool.models import Pool

_COLUMNS = "id, name, capacity, available"


class PoolRepository:
    def __init__(self, db: asyncpg.Pool) -> None:
        self._db = db

    async def create(self, name: str, capacity: int) -> Pool:
        row = await self._db.fetchrow(
            f"INSERT INTO resource_pools (name, capacity, available) "
            f"VALUES ($1, $2, $2) RETURNING {_COLUMNS}",
            name,
            capacity,
        )
        return Pool(**row)

    async def get(self, pool_id: UUID) -> Pool | None:
        row = await self._db.fetchrow(
            f"SELECT {_COLUMNS} FROM resource_pools WHERE id = $1", pool_id
        )
        return Pool(**row) if row else None