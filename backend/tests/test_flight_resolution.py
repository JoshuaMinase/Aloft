from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from mongomock_motor import AsyncMongoMockClient

from app.clients.aviationstack import AVIATIONSTACK_BASE_URL
from app.services.flight_resolution import resolve_flight_route

FLIGHT_RESPONSE = {
    "data": [
        {"flight_status": "scheduled", "departure": {"iata": "ADD"}, "arrival": {"iata": "DXB"}}
    ]
}
ADD_AIRPORT_RESPONSE = {
    "data": [
        {
            "iata_code": "ADD",
            "airport_name": "Bole International",
            "latitude": "8.9806",
            "longitude": "38.7992",
        }
    ]
}
DXB_AIRPORT_RESPONSE = {
    "data": [
        {
            "iata_code": "DXB",
            "airport_name": "Dubai International",
            "latitude": "25.2532",
            "longitude": "55.3657",
        }
    ]
}


@pytest.fixture(autouse=True)
def no_real_sleep():
    with patch("app.clients.aviationstack.asyncio.sleep", new=AsyncMock()):
        yield


@pytest.fixture
async def db():
    client = AsyncMongoMockClient()
    return client["test_aloft"]


def _airport_handler(request: httpx.Request) -> httpx.Response:
    iata = request.url.params["iata_code"]
    if iata == "ADD":
        return httpx.Response(200, json=ADD_AIRPORT_RESPONSE)
    if iata == "DXB":
        return httpx.Response(200, json=DXB_AIRPORT_RESPONSE)
    return httpx.Response(404)


@pytest.mark.asyncio
async def test_resolve_flight_route_returns_correct_coordinates(db):
    async with httpx.AsyncClient() as client:
        with respx.mock:
            respx.get(f"{AVIATIONSTACK_BASE_URL}/flights").mock(
                return_value=httpx.Response(200, json=FLIGHT_RESPONSE)
            )
            respx.get(f"{AVIATIONSTACK_BASE_URL}/airports").mock(side_effect=_airport_handler)

            departure, arrival = await resolve_flight_route(client, db, "ET409")

    assert departure == (8.9806, 38.7992)
    assert arrival == (25.2532, 55.3657)


@pytest.mark.asyncio
async def test_resolve_flight_route_caches_airport_coordinates(db):
    async with httpx.AsyncClient() as client:
        with respx.mock:
            respx.get(f"{AVIATIONSTACK_BASE_URL}/flights").mock(
                return_value=httpx.Response(200, json=FLIGHT_RESPONSE)
            )
            airport_route = respx.get(f"{AVIATIONSTACK_BASE_URL}/airports").mock(
                side_effect=_airport_handler
            )

            await resolve_flight_route(client, db, "ET409")
            assert airport_route.call_count == 2

            await resolve_flight_route(client, db, "ET409")

    # Both airports cached -- no new airport calls on second resolution.
    assert airport_route.call_count == 2


@pytest.mark.asyncio
async def test_shared_airport_only_fetched_once_across_different_routes(db):
    second_flight_response = {
        "data": [
            {"flight_status": "scheduled", "departure": {"iata": "ADD"}, "arrival": {"iata": "LHR"}}
        ]
    }
    lhr_airport_response = {
        "data": [
            {
                "iata_code": "LHR",
                "airport_name": "Heathrow",
                "latitude": "51.4700",
                "longitude": "-0.4543",
            }
        ]
    }

    def airport_handler(request: httpx.Request) -> httpx.Response:
        iata = request.url.params["iata_code"]
        if iata == "ADD":
            return httpx.Response(200, json=ADD_AIRPORT_RESPONSE)
        if iata == "DXB":
            return httpx.Response(200, json=DXB_AIRPORT_RESPONSE)
        if iata == "LHR":
            return httpx.Response(200, json=lhr_airport_response)
        return httpx.Response(404)

    async with httpx.AsyncClient() as client:
        with respx.mock:
            flight_route = respx.get(f"{AVIATIONSTACK_BASE_URL}/flights").mock(
                side_effect=[
                    httpx.Response(200, json=FLIGHT_RESPONSE),
                    httpx.Response(200, json=second_flight_response),
                ]
            )
            airport_route = respx.get(f"{AVIATIONSTACK_BASE_URL}/airports").mock(
                side_effect=airport_handler
            )

            await resolve_flight_route(client, db, "ET409")  # ADD + DXB
            await resolve_flight_route(client, db, "OTHER123")  # ADD (cached) + LHR

    assert flight_route.call_count == 2
    # 3 unique airports (ADD, DXB, LHR) -- ADD shared, only fetched once.
    assert airport_route.call_count == 3
