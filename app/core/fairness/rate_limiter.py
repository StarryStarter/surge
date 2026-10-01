from redis.asyncio import Redis

# Fixed window: the first hit opens a window of ARGV[1] seconds, every hit
# counts, and going past ARGV[2] returns the seconds until the window closes.
# Returns 0 when the request is allowed. One indivisible Redis step, so two
# simultaneous requests can't both slip past the limit.
_HIT_LUA = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
if n > tonumber(ARGV[2]) then
    return math.max(redis.call('TTL', KEYS[1]), 1)
end
return 0
"""

class RateLimiter:
    """Per-key request limiter. A fixed window allows a short burst across a
    window boundary (up to 2x the limit); that's fine for abuse protection."""

    def __init__(
        self, redis: Redis, limit: int, window_seconds: int, enabled: bool = True
    ) -> None:
        self._redis = redis
        self._script = redis.register_script(_HIT_LUA)
        self._limit = limit
        self._window = window_seconds
        self._enabled = enabled

    async def hit(self, key: str) -> int | None:
        """Count one request. None if allowed, else seconds to wait."""
        if not self._enabled:
            return None
        result = int(
            await self._script(
                keys=[f"ratelimit:{key}"], args=[self._window, self._limit]
            )
        )
        return result or None