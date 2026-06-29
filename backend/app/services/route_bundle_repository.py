from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.route_bundle import RouteBundle

_COORD_PRECISION = 2


def make_route_key(departure: tuple[float, float], arrival: tuple[float, float]) -> str:
    dep_lat, dep_lng = departure
    arr_lat, arr_lng = arrival
    return (
        f"{dep_lat:.{_COORD_PRECISION}f},{dep_lng:.{_COORD_PRECISION}f}"
        f"__{arr_lat:.{_COORD_PRECISION}f},{arr_lng:.{_COORD_PRECISION}f}"
    )


async def save_route_bundle(
    db: AsyncIOMotorDatabase,
    departure: tuple[float, float],
    arrival: tuple[float, float],
    poi_source_ids: list[str],
) -> RouteBundle:
    bundle = RouteBundle(
        route_key=make_route_key(departure, arrival),
        departure=departure,
        arrival=arrival,
        poi_source_ids=poi_source_ids,
    )
    await db.route_bundles.update_one(
        {"route_key": bundle.route_key},
        {"$set": bundle.to_mongo_dict()},
        upsert=True,
    )
    return bundle


async def get_route_bundle(db: AsyncIOMotorDatabase, route_key: str) -> RouteBundle | None:
    doc = await db.route_bundles.find_one({"route_key": route_key})
    if doc is None:
        return None
    doc.pop("_id", None)
    return RouteBundle(**doc)
