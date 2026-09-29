from uuid import UUID

from redis.asyncio import Redis

from app.core.errors import PoolNotFound, PoolSoldOut

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


def _key(pool_id: UUID) -> str:
    return f"pool:{pool_id}:available"


class AdmissionService:
    """The fast yes/no gate. Redis holds the live 'units left' counter."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._admit = redis.register_script(_ADMIT_LUA)

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

    async def available(self, pool_id: UUID) -> int:
        value = await self._redis.get(_key(pool_id))
        return int(value) if value is not None else 0