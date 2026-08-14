"""
Booking.com hotel scraper.

Uses GraphQL autocomplete to resolve destination into dest_id and dest_type,
then builds a precise search URL (same as Booking.com uses) and parses HTML results.
"""
import asyncio
import sys
import aiohttp
import logging
from typing import List, Optional, Tuple
from urllib.parse import urlencode

from app.models import Hotel
from app.scrapers.base import new_page, safe_text, parse_price, parse_rating

# ============================================================
# FIX 1: Global Windows Playwright Policy
# Applied at the top to ensure background threads have access to the correct loop.
# ============================================================
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ============================================================
# GraphQL autocomplete (captured from Network tab)
# ============================================================
AUTOCOMPLETE_URL = "https://www.booking.com/dml/graphql?lang=en-us"
AUTOCOMPLETE_OP = "AutoComplete"

AUTOCOMPLETE_QUERY = """
query AutoComplete($input: AutoCompleteRequestInput!) {
  autoCompleteSuggestions(input: $input) {
    autocompleteResponseMetadata {
      querySuggestionsEligible
      __typename
    }
    results {
      advancedSearchOutput {
        accommodations {
          adultsTotal
          autocompleteResult {
            destination {
              destId
              destType
              countryCode
              latitude
              longitude
              __typename
            }
            displayInfo {
              title
              subTitle
              showEntireHomesCheckbox
              __typename
            }
            metaData {
              webFilters
              langCode
              eligiblePages
              __typename
            }
            __typename
          }
          childrenAges
          dates {
            dateRangeCalendar {
              flexWindow
              checkin
              checkout
              __typename
            }
            broadDatesCalendar {
              losType
              los
              startWeekdays
              checkinMonths
              __typename
            }
            dateFlexUseCase
            __typename
          }
          filters
          numRooms
          sorterId
          __typename
        }
        errorMessage
        handOffAITP
        handOffWebLink
        handoffSearchDomain
        __typename
      }
      destination {
        countryCode
        destId
        destType
        latitude
        longitude
        __typename
      }
      displayInfo {
        imageUrl
        label
        labelComponents {
          name
          type
          __typename
        }
        showEntireHomesCheckbox
        title
        subTitle
        __typename
      }
      metaData {
        isSkiItem
        langCode
        maxLosData {
          extendedLoS
          __typename
        }
        metaMatches {
          id
          text
          type
          __typename
        }
        roundTrip
        webFilters
        autocompleteResultId
        autocompleteResultSource
        eligiblePages
        resultType
        __typename
      }
      __typename
    }
    __typename
  }
}
"""

# Updated headers to better mimic a real browser for GraphQL
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.booking.com",
    "Referer": "https://www.booking.com/",
}


async def resolve_destination(session: aiohttp.ClientSession, destination: str) -> Optional[Tuple[str, str]]:
    """
    Call the autocomplete GraphQL and return (dest_id, dest_type) for the first
    result that is a DISTRICT or CITY (skip individual hotels).
    """
    payload = {
        "operationName": AUTOCOMPLETE_OP,
        "query": AUTOCOMPLETE_QUERY,
        "variables": {
            "input": {
                "prefixQuery": destination,
                "requestConfig": {
                    "enableRequestContextBoost": True
                }
            }
        }
    }

    try:
        async with session.post(AUTOCOMPLETE_URL, json=payload, headers=HEADERS) as resp:
            if resp.status != 200:
                logging.warning(f"Autocomplete GraphQL blocked or failed , booking: {resp.status}. Falling back to plain text.")
                return None
            data = await resp.json()
            results = data.get("data", {}).get("autoCompleteSuggestions", {}).get("results", [])
            if not results:
                return None

            # Prefer DISTRICT or CITY, skip HOTEL
            for result in results:
                dest = result.get("destination", {})
                dest_type = dest.get("destType")
                dest_id = dest.get("destId")
                if dest_type in ("DISTRICT", "CITY") and dest_id:
                    return dest_id, dest_type

            # Fallback: first result
            first = results[0]
            dest = first.get("destination", {})
            return dest.get("destId"), dest.get("destType")

    except Exception as e:
        logging.error(f"Autocomplete error, booking: {e}")
        return None


async def _scrape_html_page(url: str, destination: str, limit: int) -> List[Hotel]:
    hotels = []
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async with new_page() as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # ============================================================
        # POPUP KILLER: Aggressive multi-selector modal closer
        # ============================================================
        try:
            # Wait 1.5 seconds for the modal/overlay to render
            await page.wait_for_timeout(1500)
            
            # List of known Booking.com modal close selectors
            popup_selectors = [
                "button[aria-label='Dismiss sign in information.']",
                "button[aria-label='Close']",
                "div[aria-label='Close'] button",
                "button[class*='close']",
                "[data-testid='bui-close-button']"
            ]
            
            for sel in popup_selectors:
                try:
                    if await page.locator(sel).count() > 0:
                        # Wait another moment to ensure the button is interactive
                        await page.wait_for_timeout(1000)
                        await page.locator(sel).first.click(timeout=2000)
                        logging.info(f"Booking.com popup closed using: {sel}")
                        break
                except Exception:
                    pass
        except Exception:
            pass
        # ============================================================

        card_selector = "div[data-testid='property-card']"
        try:
            await page.wait_for_selector(card_selector, timeout=15000)
        except Exception:
            # This is a debugging feature: Print where Playwright actually ended up.
            current_url = page.url
            logging.warning(f"Booking.com timeout. Current page URL: {current_url}")
            return hotels

        cards = page.locator(card_selector)
        count = min(await cards.count(), limit * 3)

        for i in range(count):
            if len(hotels) >= limit:
                break
            card = cards.nth(i)
            name = await safe_text(card.locator("[data-testid='title']"))
            rating_raw = await safe_text(card.locator("[data-testid='review-score'] div"))
            price_raw = await safe_text(card.locator("[data-testid='price-and-discounted-price']"))
            address = await safe_text(card.locator("[data-testid='address']"))

            if not name:
                continue

            hotels.append(
                Hotel(
                    id=f"booking-{i}",
                    name=name,
                    source="Booking.com",
                    rating=parse_rating(rating_raw),
                    price_per_night=parse_price(price_raw),
                    address=address or destination,
                )
            )

    return hotels


async def scrape(destination: str, checkin: str, checkout: str, adults: int = 2, children: int = 0, rooms: int = 1, limit: int = 5) -> List[Hotel]:
    """
    destination: free-text place, e.g. "Whitefield, Bangalore"
    checkin/checkout: "YYYY-MM-DD"
    """
    async with aiohttp.ClientSession() as session:
        # Resolve destination
        resolved = await resolve_destination(session, destination)
        if resolved:
            dest_id, dest_type = resolved
            dest_type_lower = dest_type.lower()
        else:
            dest_id = None
            dest_type_lower = None
            logging.warning("Autocomplete failed, booking; using plain text search via Playwright.")

        # Build URL exactly as Booking.com does
        base_url = "https://www.booking.com/searchresults.html"
        params = {
            "ss": destination,
            "checkin": checkin,
            "checkout": checkout,
            "group_adults": adults,
            "no_rooms": rooms,
            "group_children": children,
            "lang": "en-us",
            "aid": 304142,
            "sb": 1,
            "src": "index",
            "src_elem": "sb",
        }
        if dest_id:
            params["dest_id"] = dest_id
            params["dest_type"] = dest_type_lower

        url = f"{base_url}?{urlencode(params)}"

        return await _scrape_html_page(url, destination, limit)