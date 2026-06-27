from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.clients.wikipedia import RawPoi


class Poi(BaseModel):
    name: str
    location: dict  # GeoJSON Point: {"type": "Point", "coordinates": [lng, lat]}
    source: str
    source_id: str
    image_refs: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_wikipedia_poi(cls, raw: RawPoi) -> Poi:
        return cls(
            name=raw.title,
            location={"type": "Point", "coordinates": [raw.lng, raw.lat]},
            source="wikipedia",
            source_id=f"wikipedia:{raw.page_id}",
        )

    def to_mongo_dict(self) -> dict:
        return self.model_dump(mode="json")
