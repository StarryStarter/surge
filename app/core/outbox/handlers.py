from app.core.admission.service import AdmissionService
from app.core.outbox.models import UNIT_RETURNED, OutboxEvent

async def handle_event(admission: AdmissionService, event: OutboxEvent) -> None:
    """Carry out one event's Redis side effect. Raising means 'try again later'."""
    if event.event_type == UNIT_RETURNED:
        await admission.return_unit(event.pool_id, event.id)
        return
    raise ValueError(f"unknown outbox event type: {event.event_type}")