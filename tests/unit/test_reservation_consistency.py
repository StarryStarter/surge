from typing import Any
from uuid import UUID

import pytest

from app.core.admission.service import AdmissionService
from app.core.reservation.models import ReservationStatus
from app.core.reservation.service import ReservationService

class _BrokenReservationRepo:
    """Stands in for Postgres being down at exactly the wrong moment."""

    async def create_held(self, pool_id: UUID, requester_id: str) -> None:
        raise RuntimeError("postgres is down")

class _FailingReleaseAdmission(AdmissionService):
    """Redis blipping right when we try to hand the unit back."""

    async def release(self, pool_id: UUID) -> None:
        raise ConnectionError("redis blip")

class _FailingReturnAdmission(AdmissionService):
    """Redis blipping when an outbox event tries to return a unit."""

    async def return_unit(self, pool_id: UUID, event_id: UUID) -> bool:
        raise ConnectionError("redis blip")

def test_failed_postgres_write_does_not_leak_a_unit(run_world: Any) -> None:
    async def scenario(w: Any) -> None:
        service = ReservationService(
            _BrokenReservationRepo(), w.admission, w.outbox()  # type: ignore[arg-type]
        )

        with pytest.raises(RuntimeError, match="postgres is down"):
            await service.reserve(w.pool.id, "alice")

        rows = await w.db.fetchval(
            "SELECT count(*) FROM reservations WHERE pool_id = $1", w.pool.id
        )
        assert rows == 0
        assert await w.admission.available(w.pool.id) == 1, (
            "unit leaked: Redis gave it away but Postgres has no record of it"
        )

    run_world(scenario)

def test_original_error_survives_when_giving_the_unit_back_also_fails(
    run_world: Any,
) -> None:
    async def scenario(w: Any) -> None:
        service = ReservationService(
            _BrokenReservationRepo(),  # type: ignore[arg-type]
            _FailingReleaseAdmission(w.redis),
            w.outbox(),
        )

        # The caller must see the real cause (Postgres), not the cleanup error.
        with pytest.raises(RuntimeError, match="postgres is down"):
            await service.reserve(w.pool.id, "alice")

        # Known gap, documented on purpose: both stores failed, so the unit is
        # still missing. The reconciler is what repairs this.
        assert await w.admission.available(w.pool.id) == 0

    run_world(scenario)

def test_release_succeeds_once_postgres_committed_even_if_redis_blips(
    run_world: Any,
) -> None:
    async def scenario(w: Any) -> None:
        held = await w.service().reserve(w.pool.id, "alice")

        flaky = w.service(_FailingReturnAdmission(w.redis))
        released = await flaky.release(held.id)

        # The caller is told "released": the change is permanent, and the
        # unit's return is safely recorded in the outbox for later.
        assert released.status == ReservationStatus.RELEASED
        status = await w.db.fetchval(
            "SELECT status FROM outbox_events WHERE pool_id = $1", w.pool.id
        )
        assert status == "PENDING"

    run_world(scenario)