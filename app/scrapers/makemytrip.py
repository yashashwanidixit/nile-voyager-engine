"""
MakeMyTrip hotel scraper using internal APIs.

Uses autosuggest to resolve destination to cityCode, then fetches hotel listings
via the /search-hotels endpoint. Falls back to HTML scraping if APIs fail.
"""
import asyncio
import aiohttp
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from app.models import Hotel
from app.scrapers.base import new_page, safe_text, parse_price, parse_rating


# ============================================================
# API endpoints (captured from browser)
# ============================================================

AUTOSUGGEST_URL = "https://mapi.makemytrip.com/autosuggest/v5/search"
LISTING_URL = "https://mapi.makemytrip.com/clientbackend/cg/search-hotels/PWA/2"

# Fixed parameters from the network captures
AUTOSUGGEST_PARAMS = {
    "cc": "1",
    "exp": "4",
    "exps": "expscore2",
    "expui": "v2",
    "hcn": "0",
    "resultType": "all",
    "sgr": "t",
    "region": "IN",
    "language": "eng",
    "currency": "inr",
    "user-currency": "INR",
}

LISTING_FIXED_PARAMS = {
    "call": "onLoad",
    "language": "eng",
    "region": "in",
    "currency": "INR",
    "idContext": "B2C",
    "countryCode": "IN",
}

# Headers – update with your own User‑Agent if needed
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.makemytrip.com/",
}

# ============================================================
# Helpers
# ============================================================

def _format_mmt_date(date_str: str) -> str:
    """
    Convert standard date formats to MMDDYYYY (MakeMyTrip API format).
    Supports both DD/MM/YYYY and YYYY-MM-DD.
    """
    # Try DD/MM/YYYY first (original expected format)
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        return dt.strftime("%m%d%Y")
    except ValueError:
        pass
    
    # Fallback to YYYY-MM-DD (standard ISO format from main.py)
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%m%d%Y")
    except ValueError:
        # Last resort: assume it's already formatted correctly or raise appropriate error
        logging.warning(f"Could not parse date,mmt: {date_str}. Expecting DD/MM/YYYY or YYYY-MM-DD.")
        return date_str


async def _resolve_city_code(session: aiohttp.ClientSession, destination: str) -> Optional[str]:
    """
    Call autosuggest API and return the cityCode for the first match.
    """
    params = AUTOSUGGEST_PARAMS.copy()
    params["q"] = destination

    try:
        async with session.get(AUTOSUGGEST_URL, params=params, headers=HEADERS) as resp:
            if resp.status != 200:
                logging.error(f"Autosuggest failed, mmt: {resp.status}")
                return None
            data = await resp.json()
            suggestions = data if isinstance(data, list) else data.get("data", [])
            if not suggestions:
                return None
            return suggestions[0].get("cityCode")
    except Exception as e:
        logging.error(f"Autosuggest error, mmt: {e}")
        return None


async def _fetch_hotels_api(
    session: aiohttp.ClientSession,
    city_code: str,
    checkin: str,
    checkout: str,
    adults: int,
    children: int,
    rooms: int,
    limit: int,
) -> List[Hotel]:
    """
    Call the listing API and parse hotels from the JSON response.
    """
    params = LISTING_FIXED_PARAMS.copy()
    params["cityCode"] = city_code
    params["checkin"] = _format_mmt_date(checkin)
    params["checkout"] = _format_mmt_date(checkout)
    params["requestId"] = str(uuid.uuid4())
    
    params["rooms"] = rooms
    params["adults"] = adults
    params["children"] = children

    hotels = []
    try:
        # --- FIX: Added a 15-second timeout so we don't hang indefinitely ---
        async with session.get(LISTING_URL, params=params, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logging.error(f"Listing API failed, mmt: {resp.status}")
                return hotels

            data = await resp.json()
            response = data.get("response", {})
            sections = response.get("personalizedSections", [])
            if not sections:
                logging.warning("No personalizedSections found in response, mmt")
                return hotels

            hotel_list = []
            for section in sections:
                if section.get("hotels"):
                    hotel_list = section.get("hotels", [])
                    break

            if not hotel_list:
                logging.warning("No hotels found in response, mmt")
                return hotels

            count = 0
            for item in hotel_list:
                if count >= limit:
                    break

                name = item.get("name", "").strip()
                if not name:
                    continue

                review_summary = item.get("reviewSummary", {})
                rating_raw = review_summary.get("cumulativeRating")
                rating = parse_rating(str(rating_raw)) if rating_raw is not None else None

                price_detail = item.get("priceDetail", {})
                price_raw = price_detail.get("discountedPriceWithTax") or price_detail.get("displayPrice")
                price = parse_price(str(price_raw)) if price_raw is not None else None

                location_detail = item.get("locationDetail", {})
                city_name = location_detail.get("name", "")
                location_persuasion = item.get("locationPersuasion", [])
                area = location_persuasion[0] if location_persuasion else ""
                address = f"{area}, {city_name}".strip(", ")
                if not address:
                    address = city_name or destination

                hotels.append(
                    Hotel(
                        id=f"mmt-{item.get('id', count)}",
                        name=name,
                        source="MakeMyTrip",
                        rating=rating,
                        price_per_night=price,
                        address=address,
                    )
                )
                count += 1

            return hotels

    except asyncio.TimeoutError:
        logging.error("Listing API timeout, mmt: API did not respond within 15 seconds.")
        return hotels
    except Exception as e:
        logging.error(f"Listing API error, mmt: {e}")
        return hotels


# ============================================================
# Main scraper
# ============================================================

async def scrape(destination: str, checkin: str, checkout: str, adults: int = 2, children: int = 0, rooms: int = 1, limit: int = 5) -> List[Hotel]:
    """
    destination: free‑text place, e.g. "Whitefield, Bangalore"
    checkin/checkout: "DD/MM/YYYY" or "YYYY-MM-DD"
    Returns up to `limit` Hotel objects.
    """
    async with aiohttp.ClientSession() as session:
        city_code = await _resolve_city_code(session, destination)
        if not city_code:
            logging.warning("Could not resolve cityCode , mmt; falling back to HTML scraping.")
            return await _scrape_html_fallback(destination, checkin, checkout, adults, children, rooms, limit)

        hotels = await _fetch_hotels_api(session, city_code, checkin, checkout, adults, children, rooms, limit)
        if hotels:
            return hotels

        logging.warning("API returned no hotels, mmt; falling back to HTML scraping.")
        return await _scrape_html_fallback(destination, checkin, checkout, adults, children, rooms, limit)


# ============================================================
# Fallback: original HTML‑based scraper (kept as safety net)
# ============================================================

async def _scrape_html_fallback(destination: str, checkin: str, checkout: str, adults: int = 2, children: int = 0, rooms: int = 1, limit: int = 5) -> List[Hotel]:
    """
    Original HTML scraping – used if the API fails or returns no results.
    """
    SEARCH_URL_TEMPLATE = (
        "https://www.makemytrip.com/hotels/hotel-listing/"
        "?searchText={query}&checkin={checkin}&checkout={checkout}&rooms={rooms}&adults={adults}&children={children}"
    )
    url = SEARCH_URL_TEMPLATE.format(
        query=destination.replace(" ", "%20"),
        checkin=checkin,
        checkout=checkout,
        rooms=rooms,
        adults=adults,
        children=children
    )
    hotels: List[Hotel] = []

    async with new_page() as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # ============================================================
        # AGGRESSIVE MMT POPUP KILLER (Same as Booking/Agoda)
        # ============================================================
        try:
            # Allow a moment for the modal/overlay to render
            await page.wait_for_timeout(1500)
            
            # List of possible MMT close selectors
            popup_selectors = [
                "button.commonModal__close",
                "[data-testid='close-icon']",
                "button[aria-label='Close']",
                "button[class*='close']",
                "span.close",
                "div[class*='close']"
            ]
            
            for sel in popup_selectors:
                try:
                    if await page.locator(sel).count() > 0:
                        await page.wait_for_timeout(1000)
                        await page.locator(sel).first.click(timeout=2000)
                        logging.info(f"MMT popup closed using: {sel}")
                        break
                except Exception:
                    pass
        except Exception:
            pass
        # ============================================================

        card_selector = "div.htlListSection div.listingCardBox, div[data-testid='hotelCard']"
        try:
            await page.wait_for_selector(card_selector, timeout=15000)
        except Exception:
            # Debug: See if MMT redirected to an error page or login wall
            current_url = page.url
            logging.warning(f"MMT timeout. Current page URL: {current_url}")
            return hotels

        cards = page.locator(card_selector)
        count = min(await cards.count(), limit * 3)

        for i in range(count):
            if len(hotels) >= limit:
                break
            card = cards.nth(i)
            name = await safe_text(card.locator("h3, .hotelName"))
            rating_raw = await safe_text(card.locator(".rating, .htl-rating"))
            price_raw = await safe_text(card.locator(".price, .priceText"))
            address = await safe_text(card.locator(".address, .htl-address"))

            if not name:
                continue

            hotels.append(
                Hotel(
                    id=f"mmt-{i}",
                    name=name,
                    source="MakeMyTrip",
                    rating=parse_rating(rating_raw),
                    price_per_night=parse_price(price_raw),
                    address=address or destination,
                )
            )

    return hotels