from __future__ import annotations

from app.models.poi import Poi
from app.services.corridor import distance_km

# Within this radius of a POI, it's "below the plane" and worth narrating.
# Wider than a precise "exactly underneath" radius -- narration needs a few
# seconds' lead time to start playing before the plane has flown past.
DEFAULT_TRIGGER_RADIUS_KM = 8.0


def find_next_poi_to_narrate(
    current_lat: float,
    current_lng: float,
    route_pois: list[Poi],
    already_narrated_source_ids: set[str],
    trigger_radius_km: float = DEFAULT_TRIGGER_RADIUS_KM,
) -> Poi | None:
    """Find the closest not-yet-narrated POI within range of the current position.

    Returns the single nearest match, or None if nothing new is in range.
    If multiple POIs are simultaneously in range, only the nearest is
    returned -- narrating two things back-to-back in the same instant
    would be confusing, not additive.

    Each POI narrates at most once per session (controlled by
    already_narrated_source_ids) -- flying back over the same place
    doesn't replay the same narration on every position update.
    """
    candidates: list[tuple[float, Poi]] = []

    for poi in route_pois:
        if poi.source_id in already_narrated_source_ids:
            continue

        poi_lng, poi_lat = poi.location["coordinates"]  # GeoJSON order: [lng, lat]
        dist = distance_km(current_lat, current_lng, poi_lat, poi_lng)

        if dist <= trigger_radius_km:
            candidates.append((dist, poi))

    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]
