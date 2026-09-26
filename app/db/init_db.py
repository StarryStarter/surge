# app/db/init_db.py
"""Create the tables in the database named by DATABASE_URL: python -m app.db.init_db"""

import asyncio

import asyncpg

from app.config import get_settings
from app.db.schema import apply_schema


async def main() -> None:
    conn = await asyncpg.connect(get_settings().database_url.get_secret_value())
    try:
        await apply_schema(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())