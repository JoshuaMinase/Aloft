import pytest
from mongomock_motor import AsyncMongoMockClient

from app.clients.wikipedia import RawPoi
from app.core.db import ensure_indexes
from app.services.poi_repository import get_poi, save_poi_images, save_pois

CATHEDRAL = RawPoi(title="Cathedral", page_id=1001, lat=9.0177, lng=38.7669, distance_m=450.2)
MUSEUM = RawPoi(title="Museum", page_id=1002, lat=9.0339, lng=38.7611, distance_m=1820.7)


@pytest.fixture
async def db():
    """A fresh in-memory database per test, with the same indexes
    production actually runs -- if an index constraint matters, it should
    be exercised here too, not just assumed.
    """
    client = AsyncMongoMockClient()
    database = client["test_aloft"]
    await ensure_indexes(database)
    return database


@pytest.mark.asyncio
async def test_save_pois_inserts_new_pois(db):
    inserted = await save_pois(db, [CATHEDRAL, MUSEUM])

    assert inserted == 2
    assert await db.pois.count_documents({}) == 2


@pytest.mark.asyncio
async def test_save_pois_does_not_duplicate_on_rerun(db):
    await save_pois(db, [CATHEDRAL])
    inserted_second_time = await save_pois(db, [CATHEDRAL])  # same page_id again

    assert inserted_second_time == 0  # already existed -- refreshed, not inserted
    assert await db.pois.count_documents({}) == 1


@pytest.mark.asyncio
async def test_save_pois_stores_correct_geojson_point(db):
    await save_pois(db, [CATHEDRAL])

    doc = await db.pois.find_one({"source_id": "wikipedia:1001"})
    # GeoJSON order is (lng, lat) -- the same gotcha as corridor.py, worth
    # re-verifying here since it's a completely separate piece of code.
    assert doc["location"] == {"type": "Point", "coordinates": [38.7669, 9.0177]}


@pytest.mark.asyncio
async def test_save_pois_refreshes_fields_on_rerun(db):
    stale = RawPoi(title="Old Name", page_id=1001, lat=9.0177, lng=38.7669, distance_m=450.2)
    fresh = RawPoi(title="Corrected Name", page_id=1001, lat=9.0177, lng=38.7669, distance_m=450.2)

    await save_pois(db, [stale])
    await save_pois(db, [fresh])

    doc = await db.pois.find_one({"source_id": "wikipedia:1001"})
    assert doc["name"] == "Corrected Name"
    assert await db.pois.count_documents({}) == 1


@pytest.mark.asyncio
async def test_save_pois_handles_empty_list(db):
    inserted = await save_pois(db, [])

    assert inserted == 0
    assert await db.pois.count_documents({}) == 0



@pytest.mark.asyncio
async def test_get_poi_returns_none_when_not_found(db):
    result = await get_poi(db, "wikipedia:does-not-exist")

    assert result is None


@pytest.mark.asyncio
async def test_get_poi_returns_the_saved_poi(db):
    await save_pois(db, [CATHEDRAL])

    poi = await get_poi(db, "wikipedia:1001")

    assert poi is not None
    assert poi.name == "Cathedral"
    assert poi.source_id == "wikipedia:1001"
    assert poi.location == {"type": "Point", "coordinates": [38.7669, 9.0177]}


@pytest.mark.asyncio
async def test_save_poi_images_updates_image_refs(db):
    await save_pois(db, [CATHEDRAL])

    await save_poi_images(db, "wikipedia:1001", ["https://example.com/photo1.jpg"])

    poi = await get_poi(db, "wikipedia:1001")
    assert poi.image_refs == ["https://example.com/photo1.jpg"]


@pytest.mark.asyncio
async def test_save_poi_images_accepts_empty_list_as_honest_result(db):
    await save_pois(db, [CATHEDRAL])

    await save_poi_images(db, "wikipedia:1001", [])

    poi = await get_poi(db, "wikipedia:1001")
    assert poi.image_refs == []
