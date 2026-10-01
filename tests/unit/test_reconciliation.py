from typing import Any
from uuid import UUID

from prometheus_client import REGISTRY

from app.core.admission.service import AdmissionService, _key
from app.core.outbox.worker import OutboxWorker
from app.core.reconciliation.repository import ReconciliationRepository
from app.core.reconciliation.service import ReconciliationService
from app.core.reservation.repository import ReservationRepository

class _FailingReturnAdmission(AdmissionService):
    async def return_unit(self, pool_id: UUID, event_id: UUID) -> bool:
        raise ConnectionError("redis blip")

def _reconciler(w: Any) -> ReconciliationService:
    return ReconciliationService(
        ReconciliationRepository(w.db), w.admission, w.redis, interval=30
    )

def test_a_drift_seen_once_is_left_alone_and_repaired_when_it_repeats(
    run_world: Any,
) -> None:
    async def scenario(w: Any) -> None:
        rec = _reconciler(w)
        await w.admission.adjust(w.pool.id, -2)  # counter says 3, truth is 5
        assert await w.admission.available(w.pool.id) == 3

        assert await rec.run_once() == 0  # first sighting: could be in-flight
        assert await w.admission.available(w.pool.id) == 3

        assert await rec.run_once() == 1  # same drift again: it's real
        assert await w.admission.available(w.pool.id) == 5

    run_world(scenario, capacity=5)

def test_a_request_caught_mid_flight_is_not_mistaken_for_drift(
    run_world: Any,
) -> None:
    async def scenario(w: Any) -> None:
        rec = _reconciler(w)
        await w.admission.admit(w.pool.id)  # Redis took a unit, no row yet

        assert await rec.run_once() == 0
        assert await w.admission.available(w.pool.id) == 4

        # The request finishes: its row now exists, so the books balance.
        await ReservationRepository(w.db).create_held(w.pool.id, "alice")
        assert await rec.run_once() == 0
        assert await w.admission.available(w.pool.id) == 4  # not "repaired" to 5

    run_world(scenario, capacity=5)

def test_a_missing_counter_is_rebuilt_from_postgres_immediately(
    run_world: Any,
) -> None:
    async def scenario(w: Any) -> None:
        await ReservationRepository(w.db).create_held(w.pool.id, "alice")
        await w.redis.delete(_key(w.pool.id))

        assert await _reconciler(w).run_once() == 1
        assert await w.admission.available(w.pool.id) == 4  # 5 minus one held

    run_world(scenario, capacity=5)

def test_undelivered_returns_are_not_counted_as_drift(run_world: Any) -> None:
    async def scenario(w: Any) -> None:
        rec = _reconciler(w)
        held = await w.service().reserve(w.pool.id, "alice")
        await w.service(_FailingReturnAdmission(w.redis)).release(held.id)

        # Postgres says released, Redis hasn't heard yet: expected 0, actual 0.
        assert await rec.run_once() == 0
        assert await rec.run_once() == 0
        assert await w.admission.available(w.pool.id) == 0

        await w.db.execute("UPDATE outbox_events SET next_attempt_at = now()")
        await OutboxWorker(w.outbox(), w.admission, 0.1, 10).run_once()
        assert await w.admission.available(w.pool.id) == 1
        assert await rec.run_once() == 0  # and it still balances afterwards

    run_world(scenario)

def test_an_oversold_pool_is_reported(run_world: Any) -> None:
    async def scenario(w: Any) -> None:
        repo = ReservationRepository(w.db)
        for who in ("a", "b", "c"):  # 3 reservations against capacity 2
            await repo.create_held(w.pool.id, who)

        await _reconciler(w).run_once()

        assert REGISTRY.get_sample_value("surge_oversold_pools") == 1.0

    run_world(scenario, capacity=2)