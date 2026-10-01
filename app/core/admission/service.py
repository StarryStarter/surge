import logging
from uuid import UUID

from redis.asyncio import Redis

from app.core.errors import PoolNotFound, PoolSoldOut

logger = logging.getLogger(__name__)

_NOT_FOUND = -2
_SOLD_OUT = -1

# Runs inside Redis as ONE indivisible step: Redis finishes a script before it
# looks at any other command, so no request can slip in between the check and
# the subtract. Returns the new remaining count, or a negative code on refusal.
_ADMIT_LUA = """
local remaining = redis.call('GET', KEYS[1])
if not remaining then
    return -2
end
if tonumber(remaining) <= 0 then
    return -1
end
return redis.call('DECR', KEYS[1])
"""

# Gives one unit back, at most once per event id. KEYS[1] is the "already
# applied" marker for this event, KEYS[2] is the pool counter. Returns the new
# count, -1 if this event was already applied, -2 if the counter doesn't exist
# (we never invent stock: a missing counter stays missing).
_RETURN_LUA = """
if redis.call('EXISTS', KEYS[2]) == 0 then
    return -2
end
if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1]) then
    return redis.call('INCR', KEYS[2])
end
return -1
"""

# Applies a correction (positive or negative) to an existing counter, never
# letting it go below zero. Used by the reconciler. Returns the new count, or
# -2 if the counter doesn't exist.
_ADJUST_LUA = """
local current = redis.call('GET', KEYS[1])
if not current then
    return -2
end
local value = tonumber(current) + tonumber(ARGV[1])
if value < 0 then
    value = 0
end
redis.call('SET', KEYS[1], value)
return value
"""

_APPLIED_TTL_SECONDS = 7 * 24 * 3600

def _key(pool_id: UUID) -> str:
    return f"pool:{pool_id}:available"

def _applied_key(event_id: UUID) -> str:
    return f"outbox:applied:{event_id}"

class AdmissionService:
    """The fast yes/no gate. Redis holds the live 'units left' counter."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._admit = redis.register_script(_ADMIT_LUA)
        self._return_unit = redis.register_script(_RETURN_LUA)
        self._adjust = redis.register_script(_ADJUST_LUA)

    async def open_pool(self, pool_id: UUID, capacity: int) -> None:
        await self._redis.set(_key(pool_id), capacity)

    async def admit(self, pool_id: UUID) -> None:
        result = await self._admit(keys=[_key(pool_id)])
        if result == _NOT_FOUND:
            raise PoolNotFound(f"pool {pool_id} not found")
        if result == _SOLD_OUT:
            raise PoolSoldOut(f"pool {pool_id} is sold out")

    async def release(self, pool_id: UUID) -> None:
        await self._redis.incr(_key(pool_id))

    async def return_unit(self, pool_id: UUID, event_id: UUID) -> bool:
        """Give a unit back on behalf of one outbox event. Safe to call any
        number of times for the same event: only the first call counts."""
        result = await self._return_unit(
            keys=[_applied_key(event_id), _key(pool_id)],
            args=[_APPLIED_TTL_SECONDS],
        )
        if result == _NOT_FOUND:
            logger.warning(
                "pool %s has no Redis counter; skipping unit return for event %s "
                "(a rebuild from Postgres will account for it)",
                pool_id,
                event_id,
            )
        return result >= 0

    async def available(self, pool_id: UUID) -> int:
        value = await self._redis.get(_key(pool_id))
        return int(value) if value is not None else 0

    async def get_many(self, pool_ids: list[UUID]) -> dict[UUID, int | None]:
        """Current counters; None means the counter doesn't exist in Redis."""
        if not pool_ids:
            return {}
        values = await self._redis.mget([_key(p) for p in pool_ids])
        return {p: (int(v) if v is not None else None) for p, v in zip(pool_ids, values)}

    async def adjust(self, pool_id: UUID, delta: int) -> int:
        return int(await self._adjust(keys=[_key(pool_id)], args=[delta]))

    async def restore_if_missing(self, pool_id: UUID, value: int) -> bool:
        """Recreate a lost counter. Never overwrites one that exists."""
        return bool(await self._redis.set(_key(pool_id), value, nx=True))