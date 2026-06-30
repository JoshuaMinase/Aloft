from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.clients.wikipedia import RawPoi
from app.core.db import ensure_indexes
from app.core.dependencies import get_database, get_http_client
from app.main import app
from app.models.story import Story
from app.services.poi_repository import save_pois
from app.services.route_bundle_repository import save_route_bundle
from app.services.story_repository import save_story

ADD = (8.9806, 38.7992)
DXB = (25.2532, 55.3657)

# POI placed at (9.0, 38.0) -- tests send position pings to the same coords
NEARBY_POI = RawPoi(title="Cathedral", page_id=1001, lat=9.0, lng=38.0, distance_m=100)


@pytest.fixture
async def db():
    client = AsyncMongoMockClient()
    database = client["test_aloft"]
    await ensure_indexes(database)
    return database


@pytest.fixture
def test_client(db) -> Iterator[TestClient]:
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_http_client] = lambda: httpx.AsyncClient()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_start_session_404_for_unknown_route(test_client):
    response = test_client.post("/sessions", json={"route_key": "no-such-route"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_start_session_succeeds_for_known_route(test_client, db):
    await save_pois(db, [NEARBY_POI])
    bundle = await save_route_bundle(db, ADD, DXB, ["wikipedia:1001"])

    response = test_client.post("/sessions", json={"route_key": bundle.route_key})

    assert response.status_code == 200
    body = response.json()
    assert body["route_key"] == bundle.route_key
    assert "session_id" in body


def test_position_update_404_for_unknown_session(test_client):
    response = test_client.post(
        "/sessions/no-such-session/position", json={"lat": 9.0, "lng": 38.0}
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_position_update_triggers_nearby_poi_with_story(test_client, db):
    await save_pois(db, [NEARBY_POI])
    bundle = await save_route_bundle(db, ADD, DXB, ["wikipedia:1001"])
    await save_story(
        db,
        Story(
            poi_source_id="wikipedia:1001", language="en",
            text_content="A vivid story about the cathedral.",
            model_version="test-model",
        ),
    )
    session_id = test_client.post("/sessions", json={"route_key": bundle.route_key}).json()["session_id"]

    response = test_client.post(
        f"/sessions/{session_id}/position", json={"lat": 9.0, "lng": 38.0}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["triggered"] is True
    assert body["narration"]["source_id"] == "wikipedia:1001"
    assert body["narration"]["text_content"] == "A vivid story about the cathedral."


@pytest.mark.asyncio
async def test_position_update_not_triggered_when_nothing_nearby(test_client, db):
    await save_pois(db, [NEARBY_POI])
    bundle = await save_route_bundle(db, ADD, DXB, ["wikipedia:1001"])
    session_id = test_client.post("/sessions", json={"route_key": bundle.route_key}).json()["session_id"]

    # Far from the only POI on this route
    response = test_client.post(
        f"/sessions/{session_id}/position", json={"lat": 0.0, "lng": 0.0}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["triggered"] is False
    assert body["narration"] is None


@pytest.mark.asyncio
async def test_same_poi_does_not_retrigger_on_second_nearby_ping(test_client, db):
    await save_pois(db, [NEARBY_POI])
    bundle = await save_route_bundle(db, ADD, DXB, ["wikipedia:1001"])
    await save_story(
        db,
        Story(
            poi_source_id="wikipedia:1001", language="en",
            text_content="Story text.", model_version="test-model",
        ),
    )
    session_id = test_client.post("/sessions", json={"route_key": bundle.route_key}).json()["session_id"]

    first = test_client.post(f"/sessions/{session_id}/position", json={"lat": 9.0, "lng": 38.0})
    second = test_client.post(f"/sessions/{session_id}/position", json={"lat": 9.0, "lng": 38.0})

    assert first.json()["triggered"] is True
    assert second.json()["triggered"] is False  # already narrated this session


@pytest.mark.asyncio
async def test_triggered_poi_with_no_story_still_marks_narrated(test_client, db):
    """A POI with no story yet is still marked narrated so it's never
    silently re-offered forever. text_content comes back null instead.
    """
    await save_pois(db, [NEARBY_POI])
    bundle = await save_route_bundle(db, ADD, DXB, ["wikipedia:1001"])
    # Deliberately no save_story() call
    session_id = test_client.post("/sessions", json={"route_key": bundle.route_key}).json()["session_id"]

    first = test_client.post(f"/sessions/{session_id}/position", json={"lat": 9.0, "lng": 38.0})
    second = test_client.post(f"/sessions/{session_id}/position", json={"lat": 9.0, "lng": 38.0})

    assert first.json()["triggered"] is True
    assert first.json()["narration"]["text_content"] is None
    assert second.json()["triggered"] is False  # not re-offered despite missing content
