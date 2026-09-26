# app/core/pool/models.py
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Pool:
    id: UUID
    name: str
    capacity: int
    available: int