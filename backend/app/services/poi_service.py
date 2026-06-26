"""
Samples points along a flight route and queries the Wikipedia client at each
one to build a deduplicated list of candidate points of interest.

Why this only samples a single lane along the centerline, not the full
build_corridor() width: Wikipedia's GeoSearch caps at a 10km radius per
query (see clients/wikipedia.py). Covering build_corridor's default 100km
width properly would mean sampling multiple parallel lanes across the
corridor, multiplying API calls ~5x -- and a landmark 50km off to the side
isn't meaningfully "below the plane" anyway. So POI discovery uses its own
narrower corridor (default 20km) that matches what a single query lane can
actually cover well. The wider 100km corridor is for a different consumer
entirely: sanity-checking that a live GPS position is still roughly on the
expected route, which has nothing to do with Wikipedia's API limits.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from shapely.geometry import Polygon

from app.clients.wikipedia import MAX_RADIUS_M, RawPoi, WikipediaClientError, geosearch
from app.services.corridor import build_corridor, point_in_corridor, sample_points_by_spacing

logger = logging.getLogger("aloft.services.poi")

# How much consecutive search circles should overlap along the route, so a
# POI sitting right between two sample points still gets found by at least
# one of them.
_SAMPLE_OVERLAP_FACTOR = 1.5

# How many geosearch calls to allow in flight at once. Bounded on purpose --
# unbounded concurrency on a long route would hammer Wikipedia's servers
# with hundreds of simultaneous requests.
_DEFAULT_MAX_CONCURRENT_REQUESTS = 8


async def find_pois_along_corridor(
    client: httpx.AsyncClient,
    departure: tuple[float, float],
    arrival: tuple[float, float],
    width_km: float = 20.0,
    max_concurrent_requests: int = _DEFAULT_MAX_CONCURRENT_REQUESTS,
) -> list[RawPoi]:
    """Find candidate POIs along a route, deduplicated and filtered to the
    actual corridor polygon.

    Args:
        client: shared httpx.AsyncClient, reused across every sample point.
        departure, arrival: (lat, lng) of the route's endpoints.
        width_km: corridor width. Defaults to 20km -- matching Wikipedia's
            10km max radius on each side of the centerline. Passing
            anything wider means real coverage gaps; see the warning this
            logs if you do.
        max_concurrent_requests: bounds how many geosearch calls run at once.

    Returns:
        Deduplicated RawPoi list, filtered to points that actually fall
        inside the corridor polygon. A sample point whose geosearch call
        fails outright (after clients/wikipedia.py's own retries) is
        logged and skipped -- one bad point along a long route shouldn't
        fail the whole search.
    """
    corridor = build_corridor(departure, arrival, width_km=width_km)

    search_radius_km = min(width_km / 2, MAX_RADIUS_M / 1000)
    if search_radius_km * 2 < width_km:
        logger.warning(
            "width_km=%.0f exceeds single-lane coverage (max %.0fkm) -- only "
            "a %.0fkm-wide band along the centerline will actually be "
            "searched, not the full requested width.",
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
    """Multiple overlapping sample points will often find the same POI --
    keep one entry per page_id, the one reporting the smallest distance.
    Deterministic regardless of which sample point's request happened to
    complete first under concurrency, unlike "keep whichever we saw first."
    """
    best_by_page_id: dict[int, RawPoi] = {}
    for results in results_per_point:
        for poi in results:
            if not point_in_corridor(corridor, poi.lat, poi.lng):
                continue
            existing = best_by_page_id.get(poi.page_id)
            if existing is None or poi.distance_m < existing.distance_m:
                best_by_page_id[poi.page_id] = poi

    return list(best_by_page_id.values())
