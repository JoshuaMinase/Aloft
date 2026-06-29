from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.clients.wikipedia import WIKIPEDIA_API_URL
from app.core.db import ensure_indexes
from app.core.dependencies import get_database, get_http_client
from app.main import app

ADD = {"lat": 8.9806, "lng": 38.7992}
DXB = {"lat": 25.2532, "lng": 55.3657}

FIXED_RESPONSE = {
    "query": {
        "geosearch": [
            {"pageid": 1001, "title": "Cathedral", "lat": 9.0177, "lon": 38.7669, "dist": 450.2},
            {"pageid": 1002, "title": "Museum", "lat": 9.0339, "lon": 38.7611, "dist": 1820.7},
        ]
    }
}


@pytest.fixture(autouse=True)
def no_real_sleep():
    with patch("app.clients.wikipedia.asyncio.sleep", new=AsyncMock()):
        yield


@pytest.fixture
async def mongomock_db():
    client = AsyncMongoMockClient()
    db = client["test_aloft"]
    await ensure_indexes(db)
    return db


@pytest.fixture
def test_client(mongomock_db) -> Iterator[TestClient]:
    """Overrides the two dependencies that would otherwise need a real
    MongoDB and a connected lifespan. We deliberately don't use
    `with TestClient(app)` here -- that would trigger main.py's real
    lifespan and try to connect to an actual database.
    """
    app.dependency_overrides[get_database] = lambda: mongomock_db
    app.dependency_overrides[get_http_client] = lambda: httpx.AsyncClient()

    yield TestClient(app)

    app.dependency_overrides.clear()


def test_health_check():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_discover_pois_returns_counts_and_persists(test_client, mongomock_db):
    with respx.mock:
        respx.get(WIKIPEDIA_API_URL).mock(
            return_value=httpx.Response(200, json=FIXED_RESPONSE)
        )
        response = test_client.post(
            "/routes/pois",
            json={"departure": ADD, "arrival": DXB, "width_km": 20},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["pois_found"] == 2
    assert body["pois_newly_inserted"] == 2


def test_discover_pois_rerun_does_not_duplicate(test_client):
    with respx.mock:
        respx.get(WIKIPEDIA_API_URL).mock(
            return_value=httpx.Response(200, json=FIXED_RESPONSE)
        )
        test_client.post(
            "/routes/pois", json={"departure": ADD, "arrival": DXB, "width_km": 20}
        )
        second = test_client.post(
            "/routes/pois", json={"departure": ADD, "arrival": DXB, "width_km": 20}
        )

    assert second.json()["pois_found"] == 2
    assert second.json()["pois_newly_inserted"] == 0  # already persisted the first time


def test_discover_pois_rejects_degenerate_route_with_400(test_client):
    response = test_client.post(
        "/routes/pois", json={"departure": ADD, "arrival": ADD, "width_km": 20}
    )

    assert response.status_code == 400
    assert "same point" in response.json()["detail"]


def test_discover_pois_rejects_invalid_width_with_400(test_client):
    response = test_client.post(
        "/routes/pois", json={"departure": ADD, "arrival": DXB, "width_km": -5}
    )

    assert response.status_code == 400


def test_discover_pois_rejects_malformed_request_body(test_client):
    response = test_client.post("/routes/pois", json={"departure": ADD})  # missing arrival

    assert response.status_code == 422  # FastAPI's own validation, not ours



def test_discover_pois_returns_a_usable_route_key(test_client):
    with respx.mock:
        respx.get(WIKIPEDIA_API_URL).mock(
            return_value=httpx.Response(200, json=FIXED_RESPONSE)
        )
        response = test_client.post(
            "/routes/pois", json={"departure": ADD, "arrival": DXB, "width_km": 20}
        )

    from app.services.route_bundle_repository import make_route_key

    expected_key = make_route_key((ADD["lat"], ADD["lng"]), (DXB["lat"], DXB["lng"]))
    assert response.json()["route_key"] == expected_key
