"""
Agoda hotel scraper using Playwright (HTML scraping) via shared base.py.
"""
import logging
from typing import List
from urllib.parse import urlencode

from app.models import Hotel
from app.scrapers.base import new_page, parse_price, parse_rating

async def scrape(destination: str, checkin: str, checkout: str, adults: int = 2, children: int = 0, rooms: int = 1, limit: int = 5) -> List[Hotel]:
    """
    Scrape Agoda for hotels using Playwright to load the dynamic HTML.
    """
    hotels: List[Hotel] = []

    # Build the search URL with dynamic occupancy parameters
    base_url = "https://www.agoda.com/en-in/search"
    params = {
        "checkIn": checkin,
        "checkOut": checkout,
        "adults": adults,
        "rooms": rooms,
        "textToSearch": destination,
        "pageTypeId": "1",
        "currency": "INR",
        "cid": "1922885"
    }
    url = f"{base_url}?{urlencode(params)}"

    try:
        # === USE THE SHARED HELPER FROM base.py ===
        async with new_page() as page:
            logging.info(f"Navigating to Agoda Playwright URL: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # ============================================================
            # AGGRESSIVE AGODA POPUP KILLER (Added this block)
            # ============================================================
            try:
                # Wait 1.5 seconds for the modal/overlay to render
                await page.wait_for_timeout(1500)
                
                # List of known Agoda modal close selectors
                popup_selectors = [
                    "button[aria-label='Close']",
                    "div[data-selenium='modal-close']",
                    "span.close",
                    "button[class*='close']",
                    "div[class*='close']"
                ]
                
                for sel in popup_selectors:
                    try:
                        if await page.locator(sel).count() > 0:
                            # Wait a moment to ensure the button is interactive
                            await page.wait_for_timeout(1000)
                            await page.locator(sel).first.click(timeout=2000)
                            logging.info(f"Agoda popup closed using: {sel}")
                            break
                    except Exception:
                        pass
            except Exception:
                pass
            # ============================================================

            # Wait for hotel cards to actually load in the DOM
            try:
                # This is the standard data-selenium attribute Agoda uses for hotel cards
                await page.wait_for_selector('[data-selenium="hotel-item"]', timeout=15000)
            except Exception:
                # Added debug URL logging to see if we got redirected to a login wall
                current_url = page.url
                logging.warning(f"Timeout waiting for Agoda hotels. Current page URL: {current_url}")
                return hotels

            hotel_elements = await page.query_selector_all('[data-selenium="hotel-item"]')
            
            count = 0
            for element in hotel_elements:
                if count >= limit:
                    break
                
                try:
                    # 1. Name
                    name_el = await element.query_selector('[data-selenium="hotel-name"]')
                    name = await name_el.inner_text() if name_el else "Unknown Hotel"

                    # 2. Rating
                    rating_el = await element.query_selector('[data-selenium="review-score"]')
                    rating_text = await rating_el.inner_text() if rating_el else None
                    rating = parse_rating(rating_text) if rating_text else None

                    # 3. Price per night
                    price_el = await element.query_selector('[data-selenium="final-price"]')
                    price_text = await price_el.inner_text() if price_el else None
                    price_night = parse_price(price_text) if price_text else None

                    # 4. Address / Location
                    address_el = await element.query_selector('[data-selenium="location-text"]')
                    address = await address_el.inner_text() if address_el else destination

                    hotels.append(
                        Hotel(
                            id=f"agoda-{count}",
                            name=name.strip(),
                            source="Agoda",
                            rating=rating,
                            price_per_night=price_night,
                            address=address.strip(),
                        )
                    )
                    count += 1
                except Exception as e:
                    logging.warning(f"Skipped an Agoda hotel card due to parse error: {e}")

            logging.info(f"Agoda scraper successfully returned {len(hotels)} hotels via Playwright.")
            return hotels

    except Exception as e:
        logging.error(f"Agoda Playwright scraper failed: {e}")
        return hotels