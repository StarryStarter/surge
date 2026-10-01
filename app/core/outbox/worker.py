import asyncio
import logging

from app.core.admission.service import AdmissionService
from app.core.loop import _wait
from app.core.outbox.handlers import handle_event
from app.core.outbox.models import OutboxEvent
from app.core.outbox.repository import OutboxRepository

logger = logging.getLogger(__name__)

class OutboxWorker:
    """Background loop that keeps delivering pending outbox events."""

    def __init__(
        self,
        outbox: OutboxRepository,
        admission: AdmissionService,
        poll_interval: float,
        batch_size: int,
    ) -> None:
        self._outbox = outbox
        self._admission = admission
        self._poll_interval = poll_interval
        self._batch_size = batch_size

    async def _handle(self, event: OutboxEvent) -> None:
        await handle_event(self._admission, event)

    async def run_once(self) -> int:
        return await self._outbox.process_batch(self._handle, self._batch_size)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                processed = await self.run_once()
            except Exception:
                logger.exception("outbox worker iteration failed; will retry")
                processed = 0
            if processed == 0 and await _wait(stop, self._poll_interval):
                return