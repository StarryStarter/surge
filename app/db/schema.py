# app/db/schema.py
from pathlib import Path

import asyncpg

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


async def apply_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(_SCHEMA_PATH.read_text())

