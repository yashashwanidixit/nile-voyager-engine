"""
Road routing via GraphHopper.

Replaces the old haversine() straight-line estimate with actual road
distance + duration, which matters a lot for fare accuracy: two points 2km
apart as the crow flies can easily be a 4-5km drive around a lake/tech-park
campus in Bangalore.

Setup:
  - Free tier: sign up at https://www.graphhopper.com/ (2,500 requests/day
    free, no credit card). Set the key as GRAPHHOPPER_API_KEY env var.
  - For heavier use, self-host GraphHopper with an India OSM extract -
    removes the rate limit and the dependency on their uptime.
"""

import os
from typing import Tuple

import httpx

GRAPHHOPPER_URL = "https://graphhopper.com/api/1/route"


async def get_route(
    pickup: Tuple[float, float],
    drop: Tuple[float, float],
    api_key: str | None = None,
) -> Tuple[float, float]:
    """
    pickup / drop: (lat, lon) tuples.
    Returns (distance_km, duration_min) for a car-equivalent road route.
    Auto/Bike will realistically be a bit faster in dense traffic than this
    (they can filter through jams) - see NOTE in rides.py's per-vehicle ETA
    adjustment.
    """
    key = api_key or os.environ.get("GRAPHHOPPER_API_KEY")
    if not key:
        raise RuntimeError(
            "GraphHopper API key missing. Set GRAPHHOPPER_API_KEY env var "
            "or pass api_key= explicitly."
        )

    params = {
        "point": [f"{pickup[0]},{pickup[1]}", f"{drop[0]},{drop[1]}"],
        "vehicle": "car",
        "instructions": "false",
        "calc_points": "false",
        "key": key,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(GRAPHHOPPER_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    if "paths" not in data or not data["paths"]:
        raise ValueError(f"GraphHopper returned no route: {data}")

    path = data["paths"][0]
    distance_km = path["distance"] / 1000.0
    duration_min = path["time"] / 1000.0 / 60.0
    return distance_km, duration_min
