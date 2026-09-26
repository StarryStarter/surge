# app/core/pool/repository.py
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

    async def set_available(self, pool_id: UUID, available: int) -> None:
        await self._db.execute(
            "UPDATE resource_pools SET available = $2 WHERE id = $1", pool_id, available
        )

    async def get_for_update(self, conn: asyncpg.Connection, pool_id: UUID) -> Pool | None:
        """Reads the row AND locks it — any other request asking for this same
        row's lock has to wait until our transaction commits or rolls back."""
        row = await conn.fetchrow(
            f"SELECT {_COLUMNS} FROM resource_pools WHERE id = $1 FOR UPDATE", pool_id
        )
        return Pool(**row) if row else None

    async def decrement(self, conn: asyncpg.Connection, pool_id: UUID) -> None:
        await conn.execute(
            "UPDATE resource_pools SET available = available - 1 WHERE id = $1", pool_id
        )