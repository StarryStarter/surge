# app/db/pool.py
import asyncpg


async def create_pool(dsn: str, max_size: int) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=1, max_size=max_size)