"""
Corridor geometry: the foundation everything else (POI lookup, route bundles)
builds on.

Pure function, no I/O, no DB, no external calls -- on purpose, so it's cheap
and fast to test in isolation.
"""

from __future__ import annotations

from pyproj import Geod, Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import transform

_GEOD = Geod(ellps="WGS84")

# How many points to sample along the great-circle path.
# More points = smoother corridor, slightly more compute. 100 is overkill
# for anything shorter than a transcontinental flight and still cheap.
_DEFAULT_NUM_POINTS = 100


class DegenerateRouteError(ValueError):
    """Raised when departure and arrival are the same point (or too close to differ)."""


def build_corridor(
    departure: tuple[float, float],
    arrival: tuple[float, float],
    width_km: float = 100.0,
    num_points: int = _DEFAULT_NUM_POINTS,
) -> Polygon:
    """Build a buffered corridor polygon along the great-circle route.

    Args:
        departure: (lat, lng) of the departure airport.
        arrival: (lat, lng) of the arrival airport.
        width_km: total corridor width in kilometers (buffered width_km / 2
            on each side of the centerline).
        num_points: how many points to sample along the great-circle path.

    Returns:
        A shapely Polygon in WGS84 (lat/lng) coordinates, ready to store as
        GeoJSON in Mongo.

    Note:
        Does not handle routes crossing the antimeridian (±180° longitude).
        Not a concern for current target routes; flag if that changes.
    """
    if width_km <= 0:
        raise ValueError(f"width_km must be positive, got {width_km}")

    dep_lat, dep_lng = departure
    arr_lat, arr_lng = arrival

    if _is_same_point(dep_lat, dep_lng, arr_lat, arr_lng):
        raise DegenerateRouteError(
            f"departure {departure} and arrival {arrival} are effectively "
            "the same point -- can't build a corridor from a route with no length."
        )

    path_points = _great_circle_points(dep_lat, dep_lng, arr_lat, arr_lng, num_points)

    # shapely uses (x, y) = (lng, lat), NOT (lat, lng). Easy to get backwards.
    line_wgs84 = LineString([(lng, lat) for lat, lng in path_points])

    midpoint = path_points[len(path_points) // 2]
    to_planar, to_wgs84 = _planar_transformers(center_lat=midpoint[0], center_lng=midpoint[1])

    line_planar = transform(to_planar, line_wgs84)
    buffer_meters = (width_km * 1000) / 2
    corridor_planar = line_planar.buffer(buffer_meters, quad_segs=16)

    corridor_wgs84 = transform(to_wgs84, corridor_planar)
    return corridor_wgs84


def _is_same_point(lat1: float, lng1: float, lat2: float, lng2: float) -> bool:
    _, _, distance_m = _GEOD.inv(lng1, lat1, lng2, lat2)
    return distance_m < 1.0  # under a meter apart counts as "the same point"


def _great_circle_points(
    lat1: float, lng1: float, lat2: float, lng2: float, num_points: int
) -> list[tuple[float, float]]:
    """Evenly spaced (lat, lng) points along the real geodesic, including both ends."""
    intermediate = _GEOD.npts(lng1, lat1, lng2, lat2, num_points - 2)
    points = [(lat1, lng1)] + [(lat, lng) for lng, lat in intermediate] + [(lat2, lng2)]
    return points


def sample_points_by_spacing(
    departure: tuple[float, float],
    arrival: tuple[float, float],
    spacing_km: float,
) -> list[tuple[float, float]]:
    """Evenly spaced (lat, lng) points along the great-circle route, spaced by
    actual distance rather than a fixed count.

    build_corridor's num_points is chosen for a smooth polygon shape and
    doesn't care about real-world spacing. This is for callers like
    poi_service.py that need consistent km-spacing between query points
    regardless of whether the route is 500km or 5,000km.
    """
    if spacing_km <= 0:
        raise ValueError(f"spacing_km must be positive, got {spacing_km}")

    dep_lat, dep_lng = departure
    arr_lat, arr_lng = arrival

    _, _, total_distance_m = _GEOD.inv(dep_lng, dep_lat, arr_lng, arr_lat)
    num_points = max(2, round(total_distance_m / (spacing_km * 1000)) + 1)

    return _great_circle_points(dep_lat, dep_lng, arr_lat, arr_lng, num_points)


def _planar_transformers(center_lat: float, center_lng: float):
    """Build to/from transformers for an azimuthal-equidistant CRS centered on
    the route's midpoint -- lets us buffer in real meters regardless of where
    in the world the route is, instead of degrees (which distort by latitude).
    """
    aeqd_crs = f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lng} +units=m +ellps=WGS84"
    to_planar = Transformer.from_crs("EPSG:4326", aeqd_crs, always_xy=True).transform
    to_wgs84 = Transformer.from_crs(aeqd_crs, "EPSG:4326", always_xy=True).transform
    return to_planar, to_wgs84


def corridor_to_geojson(polygon: Polygon) -> dict:
    """Mongo's 2dsphere index wants this exact shape: lng/lat order, Polygon type."""
    return {
        "type": "Polygon",
        "coordinates": [list(polygon.exterior.coords)],
    }


def point_in_corridor(polygon: Polygon, lat: float, lng: float) -> bool:
    """Convenience wrapper so callers never have to remember the lng/lat order."""
    return polygon.contains(Point(lng, lat))
