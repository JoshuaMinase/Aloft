"""
The Poi document as stored in MongoDB. RawPoi (in clients/wikipedia.py) is
the unprocessed shape straight from the API -- this is what it becomes once
we actually persist it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.clients.wikipedia import RawPoi


class Poi(BaseModel):
    name: str
    location: dict  # GeoJSON Point: {"type": "Point", "coordinates": [lng, lat]}
    source: str
    source_id: str  # e.g. "wikipedia:1001" -- unique per source, used to upsert on save
    # Wikipedia's GeoSearch doesn't return a category -- this stays None
    # until a later piece fetches it some other way (page categories API,
    # or inferred during story generation). Not a bug, a known gap.
    category: str | None = None
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
        """Mongo doesn't know about Pydantic models -- plain dict for writes."""
        return self.model_dump()
