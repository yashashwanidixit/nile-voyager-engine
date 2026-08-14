import asyncio
import sys

# CRITICAL FIX FOR WINDOWS PLAYWRIGHT CRASH
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dataclasses import asdict
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.profiles import get_profile
from app.scrapers import makemytrip, agoda, booking
from app.ranking import select_top_hotels
from app.geocoding import geocode
from app.routing import get_route
from app.rides import estimate_all_platforms

app = FastAPI(title="Bangalore Travel Engine - Stage 1")


class HotelSearchRequest(BaseModel):
    profile_id: str
    destination: str
    checkin: str
    checkout: str
    # --- NEW FIELDS ADDED HERE ---
    adults: int = 2
    children: int = 0
    rooms: int = 1


class RideRequest(BaseModel):
    profile_id: str
    pickup_text: str
    drop_text: str
    surge_multiplier: Optional[float] = 1.0


@app.post("/hotels")
async def get_hotels(req: HotelSearchRequest):
    try:
        profile = get_profile(req.profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Pass the new adult/child/room parameters to all scrapers
    results = await asyncio.gather(
        makemytrip.scrape(req.destination, req.checkin, req.checkout, adults=req.adults, children=req.children, rooms=req.rooms, limit=5),
        agoda.scrape(req.destination, req.checkin, req.checkout, adults=req.adults, children=req.children, rooms=req.rooms, limit=5),
        booking.scrape(req.destination, req.checkin, req.checkout, adults=req.adults, children=req.children, rooms=req.rooms, limit=5),
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

    try:
        pickup = await geocode(req.pickup_text)
        drop = await geocode(req.drop_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        distance_km, duration_min = await get_route(pickup, drop)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=502, detail=str(e))

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
                "options": [{**vars(o)} for o in p.options],
            }
            for p in platforms
        ],
    }