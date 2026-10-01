from typing import Any
from uuid import UUID, uuid4

from app.core.admission.service import AdmissionService, _key
from app.core.outbox.models import OutboxEvent
from app.core.outbox.worker import OutboxWorker
from app.core.reservation.models import ReservationStatus

class _FailingReturnAdmission(AdmissionService):
    async def return_unit(self, pool_id: UUID, event_id: UUID) -> bool:
        raise ConnectionError("redis blip")

def test_release_returns_the_unit_and_replaying_the_event_does_nothing(
    run_world: Any,
) -> None:
    async def scenario(w: Any) -> None:
        service = w.service()
        held = await service.reserve(w.pool.id, "alice")
        assert await w.admission.available(w.pool.id) == 0

        await service.release(held.id)
        assert await w.admission.available(w.pool.id) == 1
        event = await w.db.fetchrow(
            "SELECT id, status FROM outbox_events WHERE pool_id = $1", w.pool.id
        )
        assert event["status"] == "DONE"

        # Simulates a worker that crashed after the Redis increment but
        # before marking the event done, then delivered it again.
        await w.admission.return_unit(w.pool.id, event["id"])
        assert await w.admission.available(w.pool.id) == 1, "double delivery oversold"

        # Control: a genuinely different event still counts.
        await w.admission.return_unit(w.pool.id, uuid4())
        assert await w.admission.available(w.pool.id) == 2

    run_world(scenario)

def test_failed_inline_delivery_is_picked_up_by_the_worker(run_world: Any) -> None:
    async def scenario(w: Any) -> None:
        held = await w.service().reserve(w.pool.id, "alice")

        released = await w.service(_FailingReturnAdmission(w.redis)).release(held.id)
        assert released.status == ReservationStatus.RELEASED
        assert await w.admission.available(w.pool.id) == 0  # not delivered yet

        row = await w.db.fetchrow(
            "SELECT status, attempts FROM outbox_events WHERE pool_id = $1", w.pool.id
        )
        assert (row["status"], row["attempts"]) == ("PENDING", 1)

        # Skip the retry backoff, then let the worker (with a healthy Redis) run.
        await w.db.execute("UPDATE outbox_events SET next_attempt_at = now()")
        worker = OutboxWorker(w.outbox(), w.admission, 0.1, 10)
        assert await worker.run_once() == 1

        assert await w.admission.available(w.pool.id) == 1
        status = await w.db.fetchval(
            "SELECT status FROM outbox_events WHERE pool_id = $1", w.pool.id
        )
        assert status == "DONE"

    run_world(scenario)

def test_missing_counter_is_skipped_not_invented(run_world: Any) -> None:
    async def scenario(w: Any) -> None:
        held = await w.service().reserve(w.pool.id, "alice")
        await w.redis.delete(_key(w.pool.id))  # Redis lost the counter

        await w.service().release(held.id)  # must not raise

        # The event is finished, and no stock was invented from nothing.
        status = await w.db.fetchval(
            "SELECT status FROM outbox_events WHERE pool_id = $1", w.pool.id
        )
        assert status == "DONE"
        assert await w.redis.exists(_key(w.pool.id)) == 0

    run_world(scenario)

def test_event_that_keeps_failing_is_dead_lettered_and_can_be_requeued(
    run_world: Any,
) -> None:
    async def scenario(w: Any) -> None:
        outbox = w.outbox(max_attempts=2)
        event_id = await w.db.fetchval(
            "INSERT INTO outbox_events (event_type, pool_id) "
            "VALUES ('UNIT_RETURNED', $1) RETURNING id",
            w.pool.id,
        )

        async def always_fails(event: OutboxEvent) -> None:
            raise RuntimeError("nope")

        assert await outbox.process_batch(always_fails, limit=10) == 1
        row = await w.db.fetchrow(
            "SELECT status, attempts FROM outbox_events WHERE id = $1", event_id
        )
        assert (row["status"], row["attempts"]) == ("PENDING", 1)

        await w.db.execute("UPDATE outbox_events SET next_attempt_at = now()")
        assert await outbox.process_batch(always_fails, limit=10) == 1
        row = await w.db.fetchrow(
            "SELECT status, attempts FROM outbox_events WHERE id = $1", event_id
        )
        assert (row["status"], row["attempts"]) == ("FAILED", 2)

        failed = await outbox.list_failed()
        assert [e.id for e in failed] == [event_id]
        assert "nope" in (failed[0].last_error or "")

        assert await outbox.requeue(event_id) is True
        row = await w.db.fetchrow(
            "SELECT status, attempts FROM outbox_events WHERE id = $1", event_id
        )
        assert (row["status"], row["attempts"]) == ("PENDING", 0)
        assert await outbox.requeue(event_id) is False  # no longer FAILED

    run_world(scenario)