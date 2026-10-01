from typing import Any

import pytest

from app.core.errors import InvalidTransition
from app.core.outbox.worker import OutboxWorker
from app.core.reservation.expiry import HoldExpiryWorker
from app.core.reservation.models import ReservationStatus
from app.core.reservation.repository import ReservationRepository

def test_an_expired_hold_returns_its_unit(run_world: Any) -> None:
    async def scenario(w: Any) -> None:
        service = w.service(hold_ttl=0)  # holds expire immediately
        held = await service.reserve(w.pool.id, "alice")
        assert await w.admission.available(w.pool.id) == 0

        repo = ReservationRepository(w.db, 0)
        assert await HoldExpiryWorker(repo, 1, 10).run_once() == 1
        assert (await repo.get(held.id)).status == ReservationStatus.EXPIRED

        # The unit comes back through the outbox, not directly.
        assert await w.admission.available(w.pool.id) == 0
        assert await OutboxWorker(w.outbox(), w.admission, 0.1, 10).run_once() == 1
        assert await w.admission.available(w.pool.id) == 1

        # And a customer who comes back too late can't confirm.
        with pytest.raises(InvalidTransition):
            await service.confirm(held.id)

    run_world(scenario)

def test_a_confirmed_reservation_never_expires(run_world: Any) -> None:
    async def scenario(w: Any) -> None:
        service = w.service(hold_ttl=0)
        held = await service.reserve(w.pool.id, "alice")
        await service.confirm(held.id)

        repo = ReservationRepository(w.db, 0)
        assert await HoldExpiryWorker(repo, 1, 10).run_once() == 0
        assert (await repo.get(held.id)).status == ReservationStatus.CONFIRMED
        assert await w.admission.available(w.pool.id) == 0

    run_world(scenario)