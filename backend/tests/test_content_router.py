from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.core.db import ensure_indexes
from app.core.dependencies import get_database, get_http_client
from app.main import app
from app.services.content_generation_service import PoiContentResult
from app.services.route_bundle_repository import save_route_bundle

ADD = (8.9806, 38.7992)
DXB = (25.2532, 55.3657)


@pytest.fixture
async def mongomock_db():
    client = AsyncMongoMockClient()
    db = client["test_aloft"]
    await ensure_indexes(db)
    return db


@pytest.fixture
def test_client(mongomock_db, auth_override) -> Iterator[TestClient]:
    app.dependency_overrides[get_database] = lambda: mongomock_db
    app.dependency_overrides[get_http_client] = lambda: httpx.AsyncClient()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_generate_content_404_for_unknown_route(test_client):
    response = test_client.post("/routes/no-such-route/content")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_content_returns_results_for_known_route(test_client, mongomock_db):
    bundle = await save_route_bundle(mongomock_db, ADD, DXB, ["wikipedia:1001", "wikipedia:1002"])

    fake_results = [
        PoiContentResult(
            poi_source_id="wikipedia:1001", story_ready=True, audio_ready=True, images_found=2
        ),
        PoiContentResult(
            poi_source_id="wikipedia:1002", story_ready=True, audio_ready=True, images_found=1
        ),
    ]
    with patch(
        "app.routers.content.generate_content_for_route", new=AsyncMock(return_value=fake_results)
    ):
        response = test_client.post(f"/routes/{bundle.route_key}/content")

    assert response.status_code == 200
    body = response.json()
    assert body["route_key"] == bundle.route_key
    assert len(body["results"]) == 2
    assert body["results"][0]["poi_source_id"] == "wikipedia:1001"
