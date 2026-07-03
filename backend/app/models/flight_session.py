from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class FlightSession(BaseModel):
    session_id: str
    route_key: str
    narrated_poi_source_ids: list[str] = Field(default_factory=list)
    upcoming_poi_triggered_source_ids: list[str] = Field(default_factory=list)
    last_region_narration_at: datetime | None = None
    last_position: tuple[float, float] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_mongo_dict(self) -> dict:
        return self.model_dump(mode="json")
