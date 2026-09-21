from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/healthz", response_model=HealthResponse)
async def healthz(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    """Liveness only: 'the process is up'. Deliberately checks no dependencies.

    Dependency checks belong in /readyz, added once Postgres/Redis exist.
    """
    return HealthResponse(status="ok", service=settings.app_name, version=__version__)
