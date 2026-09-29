import json
from typing import Any

import asyncpg


class IdempotencyRepository:
    """Backs the Idempotency-Key header: the same key always returns the
    same stored response, and the real operation never runs twice for it."""

    def __init__(self, db: asyncpg.Pool) -> None:
        self._db = db

    async def try_claim(self, key: str, requester_id: str | None) -> bool:
        """True if we're the first to see this key — go run the operation.
        False if someone already claimed it — go read their result instead."""
        result = await self._db.execute(
            "INSERT INTO idempotency_keys (key, requester_id) VALUES ($1, $2) "
            "ON CONFLICT (key) DO NOTHING",
            key,
            requester_id,
        )
        return result == "INSERT 0 1"

    async def save_response(self, key: str, response: dict[str, Any]) -> None:
        await self._db.execute(
            "UPDATE idempotency_keys SET response = $2 WHERE key = $1",
            key,
            json.dumps(response),
        )

    async def get_response(self, key: str) -> dict[str, Any] | None:
        row = await self._db.fetchrow(
            "SELECT response FROM idempotency_keys WHERE key = $1", key
        )
        if row is None or row["response"] is None:
            return None
        return json.loads(row["response"])