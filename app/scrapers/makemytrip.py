import os
import asyncio
from typing import List, Optional, Dict, Any
from apify_client import ApifyClient
from urllib.parse import quote
from app.models import Hotel
 # define this exception in __init__.py
CITY_CODES = {
    "dubai": "CTDUB",
    "manali": "CTKUU",
    "mumbai": "CTBOM",
    "goa": "CTGOI",
    "bangalore" :"CTBLR",
    # add as needed
}
AREA_CODES = {
    ("bangalore", "whitefield"): "ARWHI",
    # ("bangalore", "indiranagar"): "ARxxx",
}

class MakeMyTripSession:
    def __init__(self, api_token: Optional[str] = None, actor_id: Optional[str] = None):
        self.api_token = "apify_api_4ZLODpoMIrSb1qxdvoRGgaXJfaXizH3ZgSk1"
        self.actor_id = "Mu3k19waU0XcoDnpX"
        if not self.api_token or not self.actor_id:
            raise ValueError("APIFY_TOKEN and MAKEMYTRIP_ACTOR_ID must be set")

        self.client = ApifyClient(self.api_token)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
   
    def _parse_destination(self, destination: str):
        """
        'Whitefield, Bangalore' -> city='bangalore', area='whitefield'
        'Dubai'                 -> city='dubai', area=None
        """
        parts = [p.strip().lower() for p in destination.split(",")]
        if len(parts) == 2:
            area, city = parts
            return city, area
        return parts[0], None

    def _build_room_stay_qualifier(self, adults: int, children: int, rooms: int) -> str:
        # one segment per room: "{adults}e{children}e", segments joined by "_"
        per_room = f"{adults}e{children}e"
        return "_".join([per_room] * rooms)

    def _build_rsc(self, adults: int, children: int, rooms: int) -> str:
        # rooms, adults, children — e.g. 1 room/1 adult/0 children -> "1e1e0e"
        return f"{rooms}e{adults}e{children}e"

    def build_search_url(
        self,
        destination: str,
        checkin: str,      # MMDDYYYY
        checkout: str,      # MMDDYYYY
        adults: int = 1,
        children: int = 0,
        rooms: int = 1,
    ) -> str:
        city_key, area_key = self._parse_destination(destination)

        city_code = CITY_CODES.get(city_key)
        if not city_code:
            raise ValueError(f"Unknown city: {city_key!r}")

        room_stay_qualifier = self._build_room_stay_qualifier(adults, children, rooms)
        rsc = self._build_rsc(adults, children, rooms)

        params = {
            "checkin": checkin,
            "checkout": checkout,
            "locusId": city_code,
            "locusType": "city",
            "city": city_code,
            "country": "IN",
            "roomStayQualifier": room_stay_qualifier,
            "_uCurrency": "INR",
            "reference": "hotel",
            "rsc": rsc,
        }

        if area_key:
            area_code = AREA_CODES.get((city_key, area_key))
            if not area_code:
                raise ValueError(f"Unknown area {area_key!r} for city {city_key!r}")
            display_area = area_key.title()
            params["searchText"] = display_area
            params["mmAreaTag"] = f"{display_area}|{area_code}"  # gets %7C-encoded below
            params["type"] = "area"

        query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
        return f"https://www.makemytrip.com/hotels/hotel-listing/?{query}"

    

    async def search_hotels(
        self,
        destination: str,
        checkin: str,
        checkout: str,
        adults: int = 1,
        children: int = 0,
        rooms: int = 1,
        limit: int = 10,
    ) -> List[Hotel]:
        search_url = self.build_search_url(destination, checkin, checkout, adults, children, rooms)

        run_input = {
            "maxPages": 2,
            "resultsWanted": limit,
            "startUrls": [{"url": search_url}],
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
                "countryCode": "SG",
            },
        }

        print(f"[DEBUG] Actor input: {search_url}")

        try:
            run = await asyncio.to_thread(
                self.client.actor(self.actor_id).call, run_input=run_input
            )
            print(type(run))
        except Exception as e:
            raise SessionExpiredError(f"Apify actor call failed: {e}")

        dataset_id = run.default_dataset_id
        if not dataset_id:
            raise SessionExpiredError(f"No dataset ID on run: status={run.status}")

        dataset_id = run.default_dataset_id
        dataset = self.client.dataset(dataset_id)
        result = await asyncio.to_thread(dataset.list_items)
        items = result.items

        hotels = []
        for item in items[:limit]:
            hotels.append(
                Hotel(
                    id = item.get("hotelId"),
                    name=item.get("name") or item.get("hotelName", "Unknown"),
                    price_per_night=self._parse_price(item.get("price")),
                    rating=float(item.get("starRating", 0)) if item.get("rating") else None,
                    source="MakeMyTrip",
                    address=item.get("address", ""),
                    description=item.get("description", ""),
                    hotel_id=item.get("hotelId") or item.get("id"),
                )
            )
        return hotels

    async def book_hotel(self, hotel: Hotel) -> Dict[str, Any]:
        hotel_id = getattr(hotel, "hotel_id", None)
        if hotel_id:
            url = f"https://www.makemytrip.com/hotels/hotel-details/?hotelId={hotel_id}"
        else:
            # fallback: search by name
            url = f"https://www.makemytrip.com/hotels/hotel-list/?city={hotel.name}"
        total_cost = hotel.price_per_night * 2  # example: 2 nights
        return {"total_cost": total_cost, "page_url": url}

    @staticmethod
    def _parse_price(price_str: str) -> float:
        if not price_str:
            return 0.0
        cleaned = ''.join(c for c in price_str if c.isdigit() or c == '.')
        return float(cleaned) if cleaned else 0.0
    # app/scrapers/makemytrip.py

class SessionExpiredError(Exception):
    """Raised when the session/token is invalid or expired."""
    pass

# ... rest of your MakeMyTripSession class