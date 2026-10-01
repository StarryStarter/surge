import asyncio
import logging

from redis.asyncio import Redis

from app.core.admission.service import AdmissionService
from app.core.loop import run_periodically
from app.core.reconciliation.repository import ReconciliationRepository
from app.observability.metrics import (
    OVERSOLD_POOLS,
    RECONCILE_DRIFTED_POOLS,
    RECONCILE_HEALS,
)

logger = logging.getLogger(__name__)

_LOCK_KEY = "reconcile:lock"
_LOCK_TTL_SECONDS = 60

def _suspect_key(pool_id: object) -> str:
    return f"reconcile:suspect:{pool_id}"

class ReconciliationService:
    """Compares Redis counters with Postgres truth and repairs real drift.

    Expected counter = capacity - active reservations - undelivered returns.
    A disagreement is only repaired once the SAME disagreement is seen on two
    consecutive passes, because a request caught mid-flight (Redis updated,
    Postgres not yet) looks identical to drift for a few milliseconds and
    "fixing" it could cause an oversell. A missing counter is rebuilt right
    away: nobody can be admitted to that pool until it exists.

    Only the instance holding the Redis lock repairs anything. The others
    still do a read-only pass so their metrics stay fresh.
    """

    def __init__(
        self,
        repo: ReconciliationRepository,
        admission: AdmissionService,
        redis: Redis,
        interval: float,
    ) -> None:
        self._repo = repo
        self._admission = admission
        self._redis = redis
        self._interval = interval

    async def run_once(self) -> int:
        """One pass. Returns how many pools were repaired."""
        if await self._redis.set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL_SECONDS):
            try:
                return await self._pass(repair=True)
            finally:
                await self._redis.delete(_LOCK_KEY)
        await self._pass(repair=False)
        return 0

    async def _pass(self, repair: bool) -> int:
        snapshot = await self._repo.snapshot()
        actuals = await self._admission.get_many([s.pool_id for s in snapshot])
        suspect_ttl = int(self._interval * 3) + 10
        healed = 0
        drifted = 0
        oversold = 0

        for s in snapshot:
            expected = s.capacity - s.active - s.pending
            if expected < 0:
                oversold += 1
                if repair:
                    logger.critical(
                        "pool %s has %d active reservations for capacity %d: "
                        "OVERSOLD",
                        s.pool_id,
                        s.active,
                        s.capacity,
                    )
                expected = 0

            actual = actuals[s.pool_id]
            if actual is None:
                if repair and await self._admission.restore_if_missing(
                    s.pool_id, expected
                ):
                    healed += 1
                    RECONCILE_HEALS.labels("rebuilt").inc()
                    logger.warning(
                        "rebuilt missing Redis counter for pool %s at %d",
                        s.pool_id,
                        expected,
                    )
                continue

            delta = expected - actual
            key = _suspect_key(s.pool_id)
            if delta == 0:
                if repair:
                    await self._redis.delete(key)
                continue

            drifted += 1
            if not repair:
                continue
            previous = await self._redis.get(key)
            if previous is not None and int(previous) == delta:
                await self._admission.adjust(s.pool_id, delta)
                await self._redis.delete(key)
                healed += 1
                RECONCILE_HEALS.labels("raised" if delta > 0 else "lowered").inc()
                logger.warning(
                    "repaired pool %s: Redis had %d, expected %d (delta %+d)",
                    s.pool_id,
                    actual,
                    expected,
                    delta,
                )
            else:
                await self._redis.set(key, delta, ex=suspect_ttl)

        OVERSOLD_POOLS.set(oversold)
        RECONCILE_DRIFTED_POOLS.set(drifted)
        return healed

    async def run(self, stop: asyncio.Event) -> None:
        await run_periodically(
            self.run_once, stop, self._interval, "reconciliation", run_first=False
        )