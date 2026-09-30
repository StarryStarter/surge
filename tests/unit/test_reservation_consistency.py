import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

import asyncpg
import pytest
from redis.asyncio import Redis

from app.config import get_settings
from app.core.admission.service import AdmissionService
from app.core.pool.models import Pool
from app.core.pool.repository import PoolRepository
from app.core.reservation.service import ReservationService

class _BrokenReservationRepo:
    """Stands in for Postgres being down at exactly the wrong moment."""

    async def create_held(self, pool_id: UUID, requester_id: str) -> None:
        raise RuntimeError("postgres is down")

class _FailingReleaseAdmission(AdmissionService):
    """Redis also blipping, right when we try to hand the unit back."""

    async def release(self, pool_id: UUID) -> None:
        raise ConnectionError("redis blip")

def _run(
    db_dsn: str,
    scenario: Callable[[asyncpg.Pool, Redis, Pool], Awaitable[None]],
) -> None:
    async def runner() -> None:
        db = await asyncpg.create_pool(db_dsn, min_size=1, max_size=2)
        redis = Redis.from_url(
            get_settings().redis_url.get_secret_value(), decode_responses=True
        )
        try:
            pool = await PoolRepository(db).create("GA", capacity=1)
            await AdmissionService(redis).open_pool(pool.id, capacity=1)
            await scenario(db, redis, pool)
        finally:
            await redis.aclose()
            await db.close()

    asyncio.run(runner())

def test_failed_postgres_write_does_not_leak_a_unit(db_dsn: str) -> None:
    async def scenario(db: asyncpg.Pool, redis: Redis, pool: Pool) -> None:
        admission = AdmissionService(redis)
        service = ReservationService(_BrokenReservationRepo(), admission)  # type: ignore[arg-type]

        with pytest.raises(RuntimeError, match="postgres is down"):
            await service.reserve(pool.id, "alice")

        rows = await db.fetchval(
            "SELECT count(*) FROM reservations WHERE pool_id = $1", pool.id
        )
        assert rows == 0
        assert await admission.available(pool.id) == 1, (
            "unit leaked: Redis gave it away but Postgres has no record of it"
        )

    _run(db_dsn, scenario)

def test_original_error_survives_when_giving_the_unit_back_also_fails(
    db_dsn: str,
) -> None:
    async def scenario(db: asyncpg.Pool, redis: Redis, pool: Pool) -> None:
        service = ReservationService(
            _BrokenReservationRepo(),  # type: ignore[arg-type]
            _FailingReleaseAdmission(redis),
        )

        # The caller must see the real cause (Postgres), not the cleanup error.
        with pytest.raises(RuntimeError, match="postgres is down"):
            await service.reserve(pool.id, "alice")

        # Known gap, documented on purpose: both stores failed, so the unit is
        # still missing. Phase 11 (reconciliation) is what repairs this.
        assert await AdmissionService(redis).available(pool.id) == 0

    _run(db_dsn, scenario)