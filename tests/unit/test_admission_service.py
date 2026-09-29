import asyncio
import uuid
from collections.abc import Awaitable, Callable

import pytest
from redis.asyncio import Redis

from app.config import get_settings
from app.core.admission.service import AdmissionService
from app.core.errors import PoolNotFound, PoolSoldOut


def run_with_admission(scenario: Callable[[AdmissionService], Awaitable[None]]) -> None:
    async def runner() -> None:
        redis = Redis.from_url(
            get_settings().redis_url.get_secret_value(),
            decode_responses=True,
            max_connections=250,
        )
        try:
            await scenario(AdmissionService(redis))
        finally:
            await redis.aclose()

    asyncio.run(runner())


def test_admits_until_sold_out_then_rejects() -> None:
    async def scenario(admission: AdmissionService) -> None:
        pool_id = uuid.uuid4()
        await admission.open_pool(pool_id, capacity=2)
        await admission.admit(pool_id)
        await admission.admit(pool_id)
        with pytest.raises(PoolSoldOut):
            await admission.admit(pool_id)
        assert await admission.available(pool_id) == 0

    run_with_admission(scenario)


def test_unknown_pool_is_not_found_not_sold_out() -> None:
    async def scenario(admission: AdmissionService) -> None:
        with pytest.raises(PoolNotFound):
            await admission.admit(uuid.uuid4())

    run_with_admission(scenario)


def test_release_gives_the_unit_back() -> None:
    async def scenario(admission: AdmissionService) -> None:
        pool_id = uuid.uuid4()
        await admission.open_pool(pool_id, capacity=1)
        await admission.admit(pool_id)
        await admission.release(pool_id)
        assert await admission.available(pool_id) == 1
        await admission.admit(pool_id)  # can be taken again

    run_with_admission(scenario)


def test_concurrent_admits_never_exceed_capacity() -> None:
    """The property that matters: 200 simultaneous attempts, 10 units."""

    async def scenario(admission: AdmissionService) -> None:
        pool_id = uuid.uuid4()
        await admission.open_pool(pool_id, capacity=10)

        async def attempt() -> bool:
            try:
                await admission.admit(pool_id)
                return True
            except PoolSoldOut:
                return False

        results = await asyncio.gather(*(attempt() for _ in range(200)))
        assert sum(results) == 10
        assert await admission.available(pool_id) == 0

    run_with_admission(scenario)