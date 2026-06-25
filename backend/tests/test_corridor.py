import pytest
from pyproj import Geod
from shapely.geometry import Point

from app.services.corridor import (
    DegenerateRouteError,
    build_corridor,
    corridor_to_geojson,
    point_in_corridor,
)

# Addis Ababa Bole (ADD) -> Dubai (DXB): a real long-haul Ethiopian Airlines route.
ADD = (8.9806, 38.7992)
DXB = (25.2532, 55.3657)

# Lagos: nowhere near this route, good "should be excluded" point.
LAGOS = (6.5244, 3.3792)

GEOD = Geod(ellps="WGS84")


def test_contains_a_point_on_the_route():
    corridor = build_corridor(ADD, DXB, width_km=100)
    mid_lng, mid_lat = GEOD.npts(ADD[1], ADD[0], DXB[1], DXB[0], 1)[0]
    assert point_in_corridor(corridor, mid_lat, mid_lng)


def test_excludes_a_point_far_off_route():
    corridor = build_corridor(ADD, DXB, width_km=100)
    assert not point_in_corridor(corridor, LAGOS[0], LAGOS[1])


def test_corridor_is_valid_geometry():
    corridor = build_corridor(ADD, DXB, width_km=100)
    assert corridor.is_valid


def test_corridor_width_is_approximately_correct():
    width_km = 100
    corridor = build_corridor(ADD, DXB, width_km=width_km)

    az_fwd, _, _ = GEOD.inv(ADD[1], ADD[0], DXB[1], DXB[0])
    mid_lng, mid_lat = GEOD.npts(ADD[1], ADD[0], DXB[1], DXB[0], 1)[0]

    perpendicular_az = az_fwd + 90
    half_width_m = (width_km * 1000) / 2

    just_inside_lng, just_inside_lat, _ = GEOD.fwd(
        mid_lng, mid_lat, perpendicular_az, half_width_m * 0.9
    )
    assert point_in_corridor(corridor, just_inside_lat, just_inside_lng)

    just_outside_lng, just_outside_lat, _ = GEOD.fwd(
        mid_lng, mid_lat, perpendicular_az, half_width_m * 1.5
    )
    assert not point_in_corridor(corridor, just_outside_lat, just_outside_lng)


def test_rejects_zero_or_negative_width():
    with pytest.raises(ValueError):
        build_corridor(ADD, DXB, width_km=0)
    with pytest.raises(ValueError):
        build_corridor(ADD, DXB, width_km=-10)


def test_rejects_degenerate_route():
    with pytest.raises(DegenerateRouteError):
        build_corridor(ADD, ADD, width_km=100)


def test_geojson_output_shape_for_mongo():
    corridor = build_corridor(ADD, DXB, width_km=100)
    geojson = corridor_to_geojson(corridor)

    assert geojson["type"] == "Polygon"
    ring = geojson["coordinates"][0]
    first_lng, first_lat = ring[0]
    assert -180 <= first_lng <= 180
    assert -90 <= first_lat <= 90


def test_point_in_corridor_handles_lat_lng_order_correctly():
    corridor = build_corridor(ADD, DXB, width_km=100)
    mid_lng, mid_lat = GEOD.npts(ADD[1], ADD[0], DXB[1], DXB[0], 1)[0]
    assert corridor.contains(Point(mid_lng, mid_lat))
    assert point_in_corridor(corridor, mid_lat, mid_lng)
