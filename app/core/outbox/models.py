from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

UNIT_RETURNED = "UNIT_RETURNED"

@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: UUID
    event_type: str
    pool_id: UUID
    attempts: int

@dataclass(frozen=True, slots=True)
class FailedOutboxEvent:
    id: UUID
    event_type: str
    pool_id: UUID
    attempts: int
    last_error: str | None
    created_at: datetime