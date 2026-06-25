from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.clients.wikipedia import (
    WIKIPEDIA_API_URL,
    WikipediaClientError,
    geosearch,
)

MOCK_GEOSEARCH_RESPONSE = {
    "query": {
        "geosearch": [
            {
                "pageid": 1001,
                "title": "Holy Trinity Cathedral, Addis Ababa",
                "lat": 9.0177,
                "lon": 38.7669,
                "dist": 450.2,
            },
            {
                "pageid": 1002,
                "title": "National Museum of Ethiopia",
                "lat": 9.0339,
                "lon": 38.7611,
                "dist": 1820.7,
            },
        ]
    }
}


@pytest.fixture(autouse=True)
def no_real_sleep():
    """Every test in this file goes through retry logic that calls
    asyncio.sleep on failure -- patch it so tests run instantly instead of
    actually waiting out the backoff.
    """
    with patch("app.clients.wikipedia.asyncio.sleep", new=AsyncMock()):
        yield


@pytest.mark.asyncio
async def test_geosearch_parses_results_correctly():
    async with httpx.AsyncClient() as client:
        with respx.mock:
            respx.get(WIKIPEDIA_API_URL).mock(
                return_value=httpx.Response(200, json=MOCK_GEOSEARCH_RESPONSE)
            )
            results = await geosearch(client, lat=9.02, lng=38.76)

    assert len(results) == 2
    assert results[0].title == "Holy Trinity Cathedral, Addis Ababa"
    assert results[0].page_id == 1001
    assert results[0].distance_m == 450.2


@pytest.mark.asyncio
async def test_geosearch_returns_empty_list_when_nothing_nearby():
    async with httpx.AsyncClient() as client:
        with respx.mock:
            respx.get(WIKIPEDIA_API_URL).mock(
                return_value=httpx.Response(200, json={"query": {"geosearch": []}})
            )
            results = await geosearch(client, lat=0.0, lng=0.0)

    assert results == []


@pytest.mark.asyncio
async def test_geosearch_skips_malformed_result_but_keeps_the_rest():
    bad_response = {
        "query": {
            "geosearch": [
                {"pageid": 1, "title": "Missing Coordinates"},  # no lat/lon/dist
                MOCK_GEOSEARCH_RESPONSE["query"]["geosearch"][0],
            ]
        }
    }
    async with httpx.AsyncClient() as client:
        with respx.mock:
            respx.get(WIKIPEDIA_API_URL).mock(return_value=httpx.Response(200, json=bad_response))
            results = await geosearch(client, lat=9.02, lng=38.76)

    assert len(results) == 1
    assert results[0].title == "Holy Trinity Cathedral, Addis Ababa"


@pytest.mark.asyncio
async def test_geosearch_sends_correct_request_params_and_user_agent():
    async with httpx.AsyncClient() as client:
        with respx.mock:
            route = respx.get(WIKIPEDIA_API_URL).mock(
                return_value=httpx.Response(200, json={"query": {"geosearch": []}})
            )
            await geosearch(client, lat=9.02, lng=38.76, radius_m=5000, limit=10)

    sent_request = route.calls[0].request
    assert sent_request.url.params["gscoord"] == "9.02|38.76"
    assert sent_request.url.params["gsradius"] == "5000"
    assert sent_request.url.params["gslimit"] == "10"
    assert "AloftFlightNarrationApp" in sent_request.headers["User-Agent"]


@pytest.mark.asyncio
async def test_geosearch_rejects_radius_over_wikipedia_max():
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            await geosearch(client, lat=9.02, lng=38.76, radius_m=20_000)


@pytest.mark.asyncio
async def test_geosearch_rejects_zero_or_negative_radius():
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            await geosearch(client, lat=9.02, lng=38.76, radius_m=0)


@pytest.mark.asyncio
async def test_geosearch_retries_on_503_then_succeeds():
    async with httpx.AsyncClient() as client:
        with respx.mock:
            route = respx.get(WIKIPEDIA_API_URL).mock(
                side_effect=[
                    httpx.Response(503),
                    httpx.Response(503),
                    httpx.Response(200, json=MOCK_GEOSEARCH_RESPONSE),
                ]
            )
            results = await geosearch(client, lat=9.02, lng=38.76)

    assert route.call_count == 3
    assert len(results) == 2


@pytest.mark.asyncio
async def test_geosearch_raises_after_exhausting_all_retries():
    async with httpx.AsyncClient() as client:
        with respx.mock:
            route = respx.get(WIKIPEDIA_API_URL).mock(return_value=httpx.Response(503))
            with pytest.raises(WikipediaClientError):
                await geosearch(client, lat=9.02, lng=38.76)

    assert route.call_count == 3  # tried the full _MAX_ATTEMPTS, no more


@pytest.mark.asyncio
async def test_geosearch_does_not_retry_non_retryable_errors():
    async with httpx.AsyncClient() as client:
        with respx.mock:
            route = respx.get(WIKIPEDIA_API_URL).mock(return_value=httpx.Response(404))
            with pytest.raises(WikipediaClientError):
                await geosearch(client, lat=9.02, lng=38.76)

    assert route.call_count == 1  # a 404 won't change on retry -- fail fast
