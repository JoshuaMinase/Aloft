from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Airport(BaseModel):
    iata_code: str
    name: str
    lat: float
    lng: float
    cached_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_mongo_dict(self) -> dict:
        return self.model_dump()
