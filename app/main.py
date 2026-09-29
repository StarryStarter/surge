from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app import __version__
from app.api import errors, health, pools, reservations
from app.config import get_settings
from app.core.admission.service import AdmissionService
from app.db.pool import create_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.db_pool = await create_pool(
        settings.database_url.get_secret_value(), settings.db_pool_max_size
    )
    app.state.redis = Redis.from_url(
        settings.redis_url.get_secret_value(),
        decode_responses=True,
        max_connections=settings.redis_pool_max_size,
    )
    try:
        await app.state.redis.ping()  # fail fast at boot if Redis is unreachable
        app.state.admission = AdmissionService(app.state.redis)
        yield
    finally:
        await app.state.redis.aclose()
        await app.state.db_pool.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    errors.register(app)
    app.include_router(health.router)
    app.include_router(pools.router)
    app.include_router(reservations.router)
    return app


app = create_app()