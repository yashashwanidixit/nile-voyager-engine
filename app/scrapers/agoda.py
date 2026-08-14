import asyncio
import re
from typing import List, Optional
from datetime import datetime

from app.scrapers.hotel_scraper_base import HotelSession
from app.models import Hotel
from app.scrapers.base import parse_price, parse_rating

# ... rest of your class

class AgodaSession(HotelSession):
    def __init__(self):
        super().__init__("mmt")

    async def search_hotels(self, destination: str, checkin: str, checkout: str,
                            adults: int = 2, children: int = 0, rooms: int = 1,
                            limit: int = 5) -> List[Hotel]:
        # 1. Go to MMT homepage
        await self.page.goto("https://www.agoda.com/", wait_until="domcontentloaded")
        await self._kill_popups()  # close any modal

        # 2. Switch to Hotels tab (if not already selected)
        hotels_tab = self.page.locator("li[data-cy='hotels'] a, span:has-text('Hotels')")
        if await hotels_tab.count() > 0:
            await hotels_tab.first.click()
            await self.page.wait_for_timeout(1000)

        # 3. Fill destination
        dest_input = self.page.locator("input[data-cy='hotelCitySearch'], input[placeholder*='City/Property']")
        await dest_input.fill(destination)
        await self.page.wait_for_timeout(500)

        # 4. Select first suggestion from autocomplete
        suggestion = self.page.locator("ul.autocomplete-list li:first-child")
        if await suggestion.count() > 0:
            await suggestion.first.click()

        # 5. Set dates – use date picker (MMT expects DD/MM/YYYY format)
        # We'll open the date picker and click the specific day
        checkin_date = datetime.strptime(checkin, "%Y-%m-%d")
        checkout_date = datetime.strptime(checkout, "%Y-%m-%d")

        # Click on the check-in field to open calendar
        checkin_field = self.page.locator("input[data-cy='checkin'], #checkin, input[placeholder*='Check-in']")
        await checkin_field.click()
        await self._select_date(checkin_date)
        # Click on check-out field to open calendar
        checkout_field = self.page.locator("input[data-cy='checkout'], #checkout, input[placeholder*='Check-out']")
        await checkout_field.click()
        await self._select_date(checkout_date)

        # 6. Set guests (adults, children, rooms)
        guest_selector = self.page.locator("span[data-cy='guestCount'], button[data-cy='guest']")
        await guest_selector.click()
        await self.page.wait_for_timeout(500)

        # Set adults
        adult_plus = self.page.locator("button[data-cy='adultsPlus']")
        current_adults = int(await self.page.locator("input[data-cy='adultsCount']").get_attribute("value") or "1")
        for _ in range(adults - current_adults):
            await adult_plus.click()

        # Set children
        child_plus = self.page.locator("button[data-cy='childrenPlus']")
        current_children = int(await self.page.locator("input[data-cy='childrenCount']").get_attribute("value") or "0")
        for _ in range(children - current_children):
            await child_plus.click()

        # Set rooms
        room_plus = self.page.locator("button[data-cy='roomsPlus']")
        current_rooms = int(await self.page.locator("input[data-cy='roomsCount']").get_attribute("value") or "1")
        for _ in range(rooms - current_rooms):
            await room_plus.click()

        # Apply guest changes
        apply_btn = self.page.locator("button:has-text('Apply'), button[data-cy='guestApply']")
        if await apply_btn.count() > 0:
            await apply_btn.click()

        # 7. Click Search button
        search_btn = self.page.locator("button[data-cy='hotelSearch'], button:has-text('Search')")
        await search_btn.click()

        # 8. Wait for results
        await self.page.wait_for_selector("div.htlListSection div.listingCardBox, div[data-testid='hotelCard']", timeout=30000)

        # 9. Scrape hotel cards
        cards = self.page.locator("div.htlListSection div.listingCardBox, div[data-testid='hotelCard']")
        count = min(await cards.count(), limit * 3)
        hotels = []
        for i in range(count):
            if len(hotels) >= limit:
                break
            card = cards.nth(i)
            name = await self._safe_text(card.locator("h3, .hotelName"))
            rating_raw = await self._safe_text(card.locator(".rating, .htl-rating"))
            price_raw = await self._safe_text(card.locator(".price, .priceText"))
            address = await self._safe_text(card.locator(".address, .htl-address"))
            if not name:
                continue
            link = await card.locator("a").first.get_attribute("href")
            detail_url = None
            if link:
                if not link.startswith("http"):
                    detail_url = "https://www.agoda.com" + link
                else:
                    detail_url = link

            hotel_id = await card.get_attribute("data-hotelid") or f"mmt-{i}"
            hotels.append(
                Hotel(
                    id=hotel_id,
                    name=name,
                    source="Agoda.com",
                    rating=parse_rating(rating_raw),
                    price_per_night=parse_price(price_raw),
                    address=address or destination,
                    detail_url=detail_url,   # store it
                )
            )

    async def _select_date(self, date_obj: datetime):
        """Helper to click a date in MMT's date picker."""
        day = date_obj.day
        month = date_obj.strftime("%B")  # full month name, e.g., "June"
        year = date_obj.year
        # Click on the day cell in the calendar
        # MMT uses data-cy='datePickerDay' or simple td/button
        date_selector = f"div.DayPicker-Day:not(.DayPicker-Day--disabled) div:has-text('{day}'), button[data-cy='datePickerDay'][data-date='{year}-{date_obj.month:02d}-{day:02d}']"
        await self.page.locator(date_selector).first.click()
        await self.page.wait_for_timeout(500)

    async def _kill_popups(self):
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
                if await self.page.locator(sel).count() > 0:
                    await self.page.locator(sel).first.click()
                    await self.page.wait_for_timeout(500)
                    break
            except Exception:
                pass

    # book_hotel remains the same as before
    async def book_hotel(self, hotel: Hotel, room_choice: Optional[str] = None) -> dict:
         # Use stored detail_url, fallback to constructing
        if hotel.detail_url:
            detail_url = hotel.detail_url
        else:
            raise BookingError("No detail URL available for Agoda hotel. Please re-run the search.")
        
        await self.page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
        await self.page.wait_for_selector("div.roomCard, button[data-testid='select-room']", timeout=15000)

        # Click first available room
        selectors = [
            "button[data-testid='select-room']",
            "button:has-text('Select Room')",
            "button:has-text('Book Now')"
        ]
        room_selected = False
        for sel in selectors:
            if await self.page.locator(sel).count() > 0:
                await self.page.locator(sel).first.click()
                room_selected = True
                break
        if not room_selected:
            raise BookingError("No selectable room found.")

        await self.page.wait_for_load_state("networkidle", timeout=20000)
        total = await self._extract_total_price(".totalPrice, .grandTotal, .finalPrice")
        cart_text = await self.page.locator("body").text_content()
        return {
            "cart_items": cart_text[:1000],
            "total_cost": total,
            "packs_added": 1,
            "page_url": self.page.url,
        }

class SessionExpiredError(Exception): pass
class BookingError(Exception): pass