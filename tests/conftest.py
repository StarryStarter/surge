import asyncio
from collections.abc import AsyncIterator, Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient
from redis import Redis as SyncRedis

from app.config import get_settings
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