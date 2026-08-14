import asyncio, sys

if sys.platform == "win32":
    asyncio.set_event_loop(asyncio.ProactorEventLoop())
from dataclasses import asdict
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .profiles import get_profile
from .scrapers import makemytrip, agoda, booking
from .ranking import select_top_hotels
from .geocoding import geocode
from .routing import get_route
from .rides import estimate_all_platforms

app = FastAPI(title="Bangalore Travel Engine - Stage 1")


class HotelSearchRequest(BaseModel):
    profile_id: str          # "user_5star" | "user_4star"
    destination: str         # e.g. "Whitefield, Bangalore"
    checkin: str              # "DD/MM/YYYY" for MMT; scrapers each normalize internally
    checkout: str


class RideRequest(BaseModel):
    """
    Matches the new pipeline: user types source/destination text (image 1,
    "User input" box), we geocode both via Nominatim, route via GraphHopper,
    then estimate fares - no more raw lat/lon required from the caller.
    """
    profile_id: str
    pickup_text: str          # free-text place, e.g. "Kempegowda Airport, Bangalore"
    drop_text: str            # free-text place, e.g. the hotel address/name
    surge_multiplier: Optional[float] = 1.0


@app.post("/hotels")
async def get_hotels(req: HotelSearchRequest):
    try:
        profile = get_profile(req.profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Run all three site scrapers concurrently.
    results = await asyncio.gather(
        makemytrip.scrape(req.destination, req.checkin, req.checkout, limit=5),
        agoda.scrape(req.destination, req.checkin, req.checkout, limit=5),
        booking.scrape(req.destination, req.checkin, req.checkout, limit=5),
        return_exceptions=True,
    )

    hotels_by_source = {}
    for source_name, res in zip(["MakeMyTrip", "Agoda", "Booking.com"], results):
        hotels_by_source[source_name] = [] if isinstance(res, Exception) else res

    ranked = select_top_hotels(hotels_by_source, profile, per_source=5)

    return {
        "profile": profile.name,
        "count": len(ranked),
        "hotels": [asdict(h) for h in ranked],
    }


@app.post("/rides")
async def get_rides(req: RideRequest):
    try:
        profile = get_profile(req.profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Step 1: geocode both ends (Nominatim / OSM).
    try:
        pickup = await geocode(req.pickup_text)
        drop = await geocode(req.drop_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Step 2: road distance + duration (GraphHopper), not straight-line.
    try:
        distance_km, duration_min = await get_route(pickup, drop)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Step 3 + 4: fare estimator, grouped per platform (comparison screen).
    platforms = estimate_all_platforms(
        profile=profile,
        pickup=pickup,
        drop=drop,
        distance_km=distance_km,
        duration_min=duration_min,
        pickup_label=req.pickup_text,
        drop_label=req.drop_text,
        surge_multiplier=req.surge_multiplier or 1.0,
    )

    return {
        "profile": profile.name,
        "pickup": {"text": req.pickup_text, "lat": pickup[0], "lon": pickup[1]},
        "drop": {"text": req.drop_text, "lat": drop[0], "lon": drop[1]},
        "distance_km": round(distance_km, 2),
        "duration_min": round(duration_min, 1),
        "platforms": [
            {
                "provider": p.provider,
                "options": [
                    {**vars(o)} for o in p.options
                ],
            }
            for p in platforms
        ],
    }
