from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.dependencies import get_outbox_repo
from app.core.outbox.repository import OutboxRepository

router = APIRouter(prefix="/admin", tags=["admin"])

class FailedEventResponse(BaseModel):
    id: UUID
    event_type: str
    pool_id: UUID
    attempts: int
    last_error: str | None
    created_at: datetime

@router.get("/outbox/failed", response_model=list[FailedEventResponse])
async def list_failed(
    outbox: Annotated[OutboxRepository, Depends(get_outbox_repo)],
) -> list[FailedEventResponse]:
    events = await outbox.list_failed()
    return [
        FailedEventResponse(
            id=e.id,
            event_type=e.event_type,
            pool_id=e.pool_id,
            attempts=e.attempts,
            last_error=e.last_error,
            created_at=e.created_at,
        )
        for e in events
    ]

@router.post("/outbox/{event_id}/requeue", status_code=202)
async def requeue(
    event_id: UUID,
    outbox: Annotated[OutboxRepository, Depends(get_outbox_repo)],
) -> dict[str, str]:
    if not await outbox.requeue(event_id):
        raise HTTPException(404, "no failed event with that id")
    return {"status": "requeued"}