from __future__ import annotations

import asyncio
import logging

import httpx
from shapely.geometry import Polygon

from app.clients.wikipedia import MAX_RADIUS_M, RawPoi, WikipediaClientError, geosearch
from app.services.corridor import build_corridor, point_in_corridor, sample_points_by_spacing

logger = logging.getLogger("aloft.services.poi")

_SAMPLE_OVERLAP_FACTOR = 1.5
_DEFAULT_MAX_CONCURRENT_REQUESTS = 8


async def find_pois_along_corridor(
    client: httpx.AsyncClient,
    departure: tuple[float, float],
    arrival: tuple[float, float],
    width_km: float = 20.0,
    max_concurrent_requests: int = _DEFAULT_MAX_CONCURRENT_REQUESTS,
) -> list[RawPoi]:
    corridor = build_corridor(departure, arrival, width_km=width_km)

    search_radius_km = min(width_km / 2, MAX_RADIUS_M / 1000)
    if search_radius_km * 2 < width_km:
        logger.warning(
            "width_km=%.0f exceeds single-lane coverage (max %.0fkm) -- only "
            "a %.0fkm-wide band along the centerline will actually be searched.",
            width_km, MAX_RADIUS_M / 1000 * 2, search_radius_km * 2,
        )

    spacing_km = search_radius_km * _SAMPLE_OVERLAP_FACTOR
    sample_points = sample_points_by_spacing(departure, arrival, spacing_km=spacing_km)
    semaphore = asyncio.Semaphore(max_concurrent_requests)
    radius_m = int(search_radius_km * 1000)

    async def _search_one(point: tuple[float, float]) -> list[RawPoi]:
        lat, lng = point
        async with semaphore:
            try:
                return await geosearch(client, lat, lng, radius_m=radius_m)
            except WikipediaClientError as exc:
                logger.warning("Skipping sample point (%s, %s): %s", lat, lng, exc)
                return []

    results_per_point = await asyncio.gather(*[_search_one(p) for p in sample_points])
    return _dedupe_and_filter(results_per_point, corridor)


def _dedupe_and_filter(
    results_per_point: list[list[RawPoi]], corridor: Polygon
) -> list[RawPoi]:
    best_by_page_id: dict[int, RawPoi] = {}
    for results in results_per_point:
        for poi in results:
            if not point_in_corridor(corridor, poi.lat, poi.lng):
                continue
            existing = best_by_page_id.get(poi.page_id)
            if existing is None or poi.distance_m < existing.distance_m:
                best_by_page_id[poi.page_id] = poi
    return list(best_by_page_id.values())
