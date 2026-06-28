import pytest
from mongomock_motor import AsyncMongoMockClient

from app.core.db import ensure_indexes
from app.models.airport import Airport
from app.services.airport_repository import get_cached_airport, save_airport


@pytest.fixture
async def db():
    client = AsyncMongoMockClient()
    database = client["test_aloft"]
    await ensure_indexes(database)
    return database


@pytest.mark.asyncio
async def test_get_cached_airport_returns_none_when_not_cached(db):
    result = await get_cached_airport(db, "ADD")

    assert result is None


@pytest.mark.asyncio
async def test_save_then_get_returns_the_cached_airport(db):
    await save_airport(db, Airport(iata_code="ADD", name="Bole International", lat=8.98, lng=38.79))

    cached = await get_cached_airport(db, "ADD")

    assert cached is not None
    assert cached.name == "Bole International"
    assert cached.lat == 8.98


@pytest.mark.asyncio
async def test_save_airport_upserts_without_duplicating(db):
    await save_airport(db, Airport(iata_code="ADD", name="Old Name", lat=8.98, lng=38.79))
    await save_airport(db, Airport(iata_code="ADD", name="Corrected Name", lat=8.98, lng=38.79))

    assert await db.airports.count_documents({}) == 1
    cached = await get_cached_airport(db, "ADD")
    assert cached.name == "Corrected Name"
