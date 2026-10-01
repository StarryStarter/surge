import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

async def _wait(stop: asyncio.Event, timeout: float) -> bool:
    """Sleep up to `timeout`; return True if asked to stop meanwhile."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=timeout)
        return True
    except TimeoutError:
        return False

async def run_periodically(
    step: Callable[[], Awaitable[object]],
    stop: asyncio.Event,
    interval: float,
    name: str,
    *,
    run_first: bool = True,
) -> None:
    if not run_first and await _wait(stop, interval):
        return
    while not stop.is_set():
        try:
            await step()
        except Exception:
            logger.exception("%s iteration failed; will retry", name)
        if await _wait(stop, interval):
            return