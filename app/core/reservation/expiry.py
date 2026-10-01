import asyncio
import logging

from app.core.loop import run_periodically
from app.core.reservation.repository import ReservationRepository
from app.observability.metrics import HOLDS_EXPIRED

logger = logging.getLogger(__name__)

class HoldExpiryWorker:
    """Expires holds nobody confirmed. Freed units flow back through the outbox."""

    def __init__(
        self, reservations: ReservationRepository, interval: float, batch_size: int
    ) -> None:
        self._reservations = reservations
        self._interval = interval
        self._batch_size = batch_size

    async def run_once(self) -> int:
        expired = await self._reservations.expire_due_holds(self._batch_size)
        if expired:
            HOLDS_EXPIRED.inc(expired)
            logger.info("expired %d reservation hold(s)", expired)
        return expired

    async def run(self, stop: asyncio.Event) -> None:
        await run_periodically(self.run_once, stop, self._interval, "hold expiry")