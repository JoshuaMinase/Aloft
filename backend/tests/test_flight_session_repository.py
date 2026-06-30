import pytest
from mongomock_motor import AsyncMongoMockClient

from app.core.db import ensure_indexes
from app.services.flight_session_repository import (
    create_session,
    get_session,
    record_position_and_narration,
)


@pytest.fixture
async def db():
    client = AsyncMongoMockClient()
    database = client["test_aloft"]
    await ensure_indexes(database)
    return database


@pytest.mark.asyncio
async def test_create_session_returns_unique_session_ids(db):
    s1 = await create_session(db, "route-key-1")
    s2 = await create_session(db, "route-key-1")

    assert s1.session_id != s2.session_id


@pytest.mark.asyncio
async def test_create_session_starts_with_empty_narrated_list(db):
    session = await create_session(db, "route-key-1")

    assert session.narrated_poi_source_ids == []
    assert session.last_position is None


@pytest.mark.asyncio
async def test_get_session_returns_none_when_not_found(db):
    assert await get_session(db, "no-such-session") is None


@pytest.mark.asyncio
async def test_get_session_roundtrips_correctly(db):
    created = await create_session(db, "route-key-1")

    fetched = await get_session(db, created.session_id)

    assert fetched is not None
    assert fetched.route_key == "route-key-1"


@pytest.mark.asyncio
async def test_record_position_updates_last_position(db):
    session = await create_session(db, "route-key-1")

    await record_position_and_narration(db, session.session_id, 9.0, 38.0, None)

    updated = await get_session(db, session.session_id)
    assert updated.last_position == (9.0, 38.0)


@pytest.mark.asyncio
async def test_record_position_adds_newly_narrated_poi(db):
    session = await create_session(db, "route-key-1")

    await record_position_and_narration(db, session.session_id, 9.0, 38.0, "wikipedia:1001")

    updated = await get_session(db, session.session_id)
    assert "wikipedia:1001" in updated.narrated_poi_source_ids


@pytest.mark.asyncio
async def test_record_position_does_not_duplicate_poi_narrated_twice(db):
    session = await create_session(db, "route-key-1")

    await record_position_and_narration(db, session.session_id, 9.0, 38.0, "wikipedia:1001")
    await record_position_and_narration(db, session.session_id, 9.01, 38.01, "wikipedia:1001")

    updated = await get_session(db, session.session_id)
    assert updated.narrated_poi_source_ids.count("wikipedia:1001") == 1


@pytest.mark.asyncio
async def test_record_position_accumulates_multiple_distinct_pois(db):
    session = await create_session(db, "route-key-1")

    await record_position_and_narration(db, session.session_id, 9.0, 38.0, "wikipedia:1001")
    await record_position_and_narration(db, session.session_id, 12.0, 43.0, "wikipedia:1002")

    updated = await get_session(db, session.session_id)
    assert set(updated.narrated_poi_source_ids) == {"wikipedia:1001", "wikipedia:1002"}
