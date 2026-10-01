import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app
from redis.asyncio import Redis

from app import __version__
from app.api import admin, errors, health, pools, reservations
from app.config import get_settings
from app.core.admission.service import AdmissionService
from app.core.outbox.repository import OutboxRepository
from app.core.outbox.worker import OutboxWorker
from app.core.reconciliation.repository import ReconciliationRepository
from app.core.reconciliation.service import ReconciliationService
from app.core.reservation.expiry import HoldExpiryWorker
from app.core.reservation.repository import ReservationRepository
from app.db.pool import create_pool
from app.core.fairness.rate_limiter import RateLimiter

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
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    try:
        await app.state.redis.ping()  # fail fast at boot if Redis is unreachable
        db = app.state.db_pool
        admission = AdmissionService(app.state.redis)
        app.state.admission = admission
        
        app.state.rate_limiter = RateLimiter(
            app.state.redis,
            settings.rate_limit_requests,
            settings.rate_limit_window_seconds,
            settings.rate_limit_enabled,
        )

        outbox_worker = OutboxWorker(
            OutboxRepository(db, settings.outbox_max_attempts),
            admission,
            settings.outbox_poll_interval_seconds,
            settings.outbox_batch_size,
        )
        expiry_worker = HoldExpiryWorker(
            ReservationRepository(db, settings.hold_ttl_seconds),
            settings.hold_expiry_interval_seconds,
            settings.hold_expiry_batch_size,
        )
        tasks.append(asyncio.create_task(outbox_worker.run(stop)))
        tasks.append(asyncio.create_task(expiry_worker.run(stop)))
        if settings.reconcile_enabled:
            reconciler = ReconciliationService(
                ReconciliationRepository(db),
                admission,
                app.state.redis,
                settings.reconcile_interval_seconds,
            )
            tasks.append(asyncio.create_task(reconciler.run(stop)))
        yield
    finally:
        stop.set()
        for task in tasks:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(task, timeout=5)
        await app.state.redis.aclose()
        await app.state.db_pool.close()

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    errors.register(app)
    app.include_router(health.router)
    app.include_router(pools.router)
    app.include_router(reservations.router)
    app.include_router(admin.router)
    app.mount("/metrics", make_asgi_app())
    return app

app = create_app()