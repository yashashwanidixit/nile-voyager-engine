"""
Geocoding via OpenStreetMap's Nominatim search API.

IMPORTANT — usage policy constraints (these are real limits, not suggestions):
  - The public https://nominatim.openstreetmap.org endpoint is rate-limited to
    ~1 request/second and REQUIRES a descriptive User-Agent identifying your
    app (no browser-spoofing). Violating this gets your IP blocked.
  - It's meant for light/occasional use. For anything beyond a prototype with
    real traffic, self-host Nominatim or use a paid provider (LocationIQ,
    Mapbox, Google Geocoding) that mirrors the same OSM data with proper SLAs.
  - Cache geocoded results (e.g. by normalized place string) since the same
    "Whitefield, Bangalore" will be looked up repeatedly.
"""

from typing import Tuple

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Nominatim requires a real, identifying User-Agent per their usage policy.
# Replace with your actual app name / contact email before shipping.
_HEADERS = {"User-Agent": "bangalore-travel-engine/1.0 (contact: [email protected])"}


async def geocode(place: str, bias_bangalore: bool = True) -> Tuple[float, float]:
    """
    Resolves a free-text place string to (lat, lon).
    Raises ValueError if nothing is found.
    """
    params = {"q": place, "format": "json", "limit": 1}
    if bias_bangalore:
        # Viewbox bias keeps ambiguous names (e.g. "Whitefield") resolving to
        # the Bangalore one instead of a same-named place elsewhere in India.
        params["viewbox"] = "77.35,13.15,77.85,12.75"  # left,top,right,bottom around Bengaluru
        params["bounded"] = 0  # bias, don't hard-restrict

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(NOMINATIM_URL, params=params, headers=_HEADERS)
        resp.raise_for_status()
        data = resp.json()

    if not data:
        raise ValueError(f"Could not geocode '{place}'")

    return float(data[0]["lat"]), float(data[0]["lon"])
