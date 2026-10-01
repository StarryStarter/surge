import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient
from redis import Redis as SyncRedis
from redis.asyncio import Redis

from app.config import get_settings
from app.core.admission.service import AdmissionService
from app.core.outbox.repository import OutboxRepository
from app.core.pool.models import Pool
from app.core.pool.repository import PoolRepository
from app.core.reservation.repository import ReservationRepository
from app.core.reservation.service import ReservationService
from app.db.schema import apply_schema
from app.main import create_app

def _test_dsn() -> str:
    settings = get_settings()
    if settings.test_database_url is None:
        raise RuntimeError(
            "TEST_DATABASE_URL is not set. Point it at a disposable database "
            "(see .env.example) — never at your dev database."
        )
    return settings.test_database_url.get_secret_value()

async def _apply_schema_async(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        await apply_schema(conn)
    finally:
        await conn.close()

async def _truncate_async(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("TRUNCATE reservations, resource_pools CASCADE")
    finally:
        await conn.close()

@pytest.fixture(scope="session", autouse=True)
def _prepare_test_schema() -> None:
    asyncio.run(_apply_schema_async(_test_dsn()))

@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    """Every test starts with empty tables — no ordering dependence between tests."""
    asyncio.run(_truncate_async(_test_dsn()))

@pytest.fixture(autouse=True)
def _isolated_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the whole app/test process at a separate Redis database and
    empty it before every test."""
    get_settings.cache_clear()
    settings = get_settings()
    if settings.test_redis_url is None:
        raise RuntimeError(
            "TEST_REDIS_URL is not set. Use a different Redis database than "
            "REDIS_URL (see .env.example), e.g. redis://localhost:6379/15."
        )
    dev_url = settings.redis_url.get_secret_value()
    test_url = settings.test_redis_url.get_secret_value()
    if test_url == dev_url:
        raise RuntimeError(
            "TEST_REDIS_URL is identical to REDIS_URL. Refusing to flush your "
            "dev Redis — point TEST_REDIS_URL at a different database index."
        )

    flusher = SyncRedis.from_url(test_url)
    try:
        flusher.flushdb()
    finally:
        flusher.close()

    monkeypatch.setenv("REDIS_URL", test_url)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

@pytest.fixture
def db_dsn() -> str:
    return _test_dsn()

@pytest.fixture
async def db_pool() -> AsyncIterator[asyncpg.Pool]:
    pool = await asyncpg.create_pool(_test_dsn(), min_size=1, max_size=5)
    try:
        yield pool
    finally:
        await pool.close()

@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Point the app at the TEST database, not whatever DATABASE_URL the
    # developer has in their local .env. (REDIS_URL is already redirected
    # by the autouse _isolated_redis fixture.)
    monkeypatch.setenv("DATABASE_URL", _test_dsn())
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()

@dataclass
class World:
    """Everything a service-level test needs: live connections to the test
    Postgres and test Redis, plus one freshly opened pool."""

    db: asyncpg.Pool
    redis: Redis
    pool: Pool
    admission: AdmissionService

    def outbox(self, max_attempts: int = 8) -> OutboxRepository:
        return OutboxRepository(self.db, max_attempts)

    def service(
        self, admission: AdmissionService | None = None, hold_ttl: int = 900
    ) -> ReservationService:
        return ReservationService(
            ReservationRepository(self.db, hold_ttl),
            admission or self.admission,
            self.outbox(),
        )

@pytest.fixture
def run_world(db_dsn: str) -> Callable[..., None]:
    """Run an async scenario against a fresh pool.

        def test_x(run_world):
            async def scenario(w): ...
            run_world(scenario, capacity=5)
    """

    def run(scenario: Callable[[Any], Awaitable[None]], capacity: int = 1) -> None:
        async def runner() -> None:
            db = await asyncpg.create_pool(db_dsn, min_size=1, max_size=3)
            redis = Redis.from_url(
                get_settings().redis_url.get_secret_value(), decode_responses=True
            )
            try:
                pool = await PoolRepository(db).create("GA", capacity=capacity)
                admission = AdmissionService(redis)
                await admission.open_pool(pool.id, capacity=capacity)
                await scenario(World(db, redis, pool, admission))
            finally:
                await redis.aclose()
                await db.close()

        asyncio.run(runner())

    return run