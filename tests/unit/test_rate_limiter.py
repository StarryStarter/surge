from typing import Any

from app.core.fairness.rate_limiter import RateLimiter

def test_limiter_blocks_past_the_limit_per_key(run_world: Any) -> None:
    async def scenario(w: Any) -> None:
        limiter = RateLimiter(w.redis, limit=3, window_seconds=60)

        for _ in range(3):
            assert await limiter.hit("alice") is None
        retry_after = await limiter.hit("alice")
        assert retry_after is not None and 1 <= retry_after <= 60

        assert await limiter.hit("bob") is None  # other keys are unaffected

        disabled = RateLimiter(w.redis, limit=1, window_seconds=60, enabled=False)
        for _ in range(5):
            assert await disabled.hit("carol") is None

    run_world(scenario)