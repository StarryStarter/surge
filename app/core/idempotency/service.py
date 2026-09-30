import json
from typing import Any

from redis.asyncio import Redis

_TTL_SECONDS = 24 * 60 * 60  # keep replay data for a day; long enough for any real retry


def _key(idempotency_key: str) -> str:
    return f"idem:{idempotency_key}"


class IdempotencyService:
    """Fast idempotency claim + cache, entirely in Redis. A rejected request
    (e.g. sold out) never has to touch Postgres to get rejected."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_cached_response(self, key: str) -> dict[str, Any] | None:
        raw = await self._redis.get(_key(key))
        if raw is None:
            return None
        return json.loads(raw)

    async def try_claim(self, key: str) -> bool:
        """True if we're first to see this key. SET ... NX is atomic — same
        guarantee the Postgres UNIQUE constraint gave us, just in Redis."""
        claimed = await self._redis.set(_key(key), "null", nx=True, ex=_TTL_SECONDS)
        return claimed is True

    async def release_claim(self, key: str) -> None:
        """If the actual operation fails after we claimed the key, undo the
        claim so a legitimate retry isn't stuck replaying nothing forever."""
        await self._redis.delete(_key(key))

    async def save_response(self, key: str, response: dict[str, Any]) -> None:
        await self._redis.set(_key(key), json.dumps(response), ex=_TTL_SECONDS)