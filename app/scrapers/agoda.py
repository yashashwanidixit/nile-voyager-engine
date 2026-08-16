import asyncio
import re
from typing import List, Optional
from datetime import datetime

from app.scrapers.hotel_scraper_base import HotelSession, SessionExpiredError, BookingError
from app.models import Hotel
from app.scrapers.base import parse_price, parse_rating


class AgodaSession(HotelSession):
    def __init__(self):
        super().__init__("agoda")

    async def search_hotels(self, destination: str, checkin: str, checkout: str,
                            adults: int = 2, children: int = 0, rooms: int = 1,
                            limit: int = 10) -> List[Hotel]:
        # 1. Go to Agoda homepage
        await self.page.goto("https://www.agoda.com/", wait_until="domcontentloaded")
        await self._kill_popups()

        # Ensure we are strictly on the "Hotels" tab (and not Flight + Hotel)
        await self.page.evaluate("""
            () => {
                const hotelTab = document.querySelector(
                    'button[data-selenium="hotel-tab"], ' +
                    'button[data-element-name="hotel-tab"], ' +
                    '[data-element-name="tab-hotels"]'
                );
                if (hotelTab && hotelTab.getAttribute('aria-selected') !== 'true') {
                    hotelTab.click();
                }
            }
        """)
        await self.page.wait_for_timeout(300)

        # 2. Fill destination
        dest_input = self.page.locator(
            "input[placeholder*='Enter a destination'], "
            "input[data-cy='hotelCitySearch'], "
            "input[aria-label='Search'], "
            "input[data-selenium='textInput']"
        ).first
        await dest_input.fill(destination)
        await self.page.wait_for_timeout(800)  # wait for autocomplete dropdown

        # Select first autocomplete suggestion
        clicked = await self.page.evaluate("""
            (destination) => {
                const selectors = [
                    'ul[data-selenium="autocomplete-result"] li',
                    'li[data-selenium="autosuggest-item"]',
                    'div[role="listbox"] > div, div[role="listbox"] > li',
                    'li[role="option"], div[role="option"]',
                    'ul[class*="autocomplete"] li, div[class*="autocomplete"] li'
                ];
                for (const sel of selectors) {
                    const elements = document.querySelectorAll(sel);
                    for (const el of elements) {
                        if (el.textContent.trim().toLowerCase().includes(destination.toLowerCase())) {
                            el.click();
                            return true;
                        }
                    }
                }
                const firstOpt = document.querySelector('li[role="option"], ul[data-selenium="autocomplete-result"] li');
                if (firstOpt) {
                    firstOpt.click();
                    return true;
                }
                return false;
            }
        """, destination)

        if not clicked:
            print("⚠️ Could not find autocomplete suggestion; pressing Enter as fallback.")
            await dest_input.press("Enter")
        else:
            print("✅ Clicked autocomplete suggestion.")
        await self.page.wait_for_timeout(500)

        # 3. Set check-in and check-out dates
        checkin_date = datetime.strptime(checkin, "%Y-%m-%d")
        checkout_date = datetime.strptime(checkout, "%Y-%m-%d")

        await self._select_date_agoda(checkin_date)
        await self._select_date_agoda(checkout_date)

        # 4. Open Guest Picker
        await self.page.evaluate("""
            () => {
                const openPicker = document.querySelector('[role="dialog"][aria-label*="guests"], div[class*="guestPickerOpen"]');
                if (openPicker) return;

                const guestBtn = document.querySelector(
                    'div[data-selenium="occupancyBox"], ' +
                    'button[data-selenium="guestPicker"], ' +
                    'button[data-testid="guest-picker"], ' +
                    'div[data-element-name="occupancy-box"]'
                );
                if (guestBtn) {
                    guestBtn.click();
                }
            }
        """)
        await self.page.wait_for_timeout(400)

        # 5. Adjust guests (Default on Agoda: 2 adults, 0 children, 1 room)
        adult_clicks_needed = max(0, adults - 1)
        adult_minus_needed = 1 if adults == 1 else 0
        child_clicks_needed = children
        room_clicks_needed = max(0, rooms - 1)

        print(f"🔧 Guest adjustment: Adults (+{adult_clicks_needed} / -{adult_minus_needed}), Children (+{child_clicks_needed}), Rooms (+{room_clicks_needed})")

        # Execute guest updates strictly scoped inside the guest dialog
        adjust_result = await self.page.evaluate(
            """
            (config) => {
                const { adultPlus, adultMinus, childPlus, roomPlus } = config;
                const log = [];

                // Scope to the occupancy / guest popup ONLY
                const modal = document.querySelector(
                    'div[data-selenium="occupancyBox"] [role="dialog"], ' +
                    'div[data-selenium="occupancyBox"], ' +
                    'div[class*="OccupancySelector"], ' +
                    'div[class*="guestPicker"], ' +
                    '[role="dialog"][aria-label*="guest" i]'
                ) || document.body;

                function getPlusButton(category) {
                    // Try exact Agoda data-selenium attributes first
                    const selectors = [
                        `button[data-selenium="occupancy-${category}-plus"]`,
                        `button[data-selenium="occupancy-${category}-increase"]`,
                        `button[data-element-name="occupancy-${category}-increase"]`,
                        `button[data-element-name="occupancy-${category}-plus"]`,
                        `[data-element-name="occupancy-${category}"] button[data-selenium="plus"]`,
                        `button[aria-label*="Increase ${category}" i]`,
                        `button[aria-label*="Add ${category}" i]`
                    ];
                    for (const sel of selectors) {
                        const btn = modal.querySelector(sel);
                        if (btn && btn.offsetParent !== null && !btn.disabled) return btn;
                    }

                    // Fallback: look for category label, then find exact '+' button strictly inside that section
                    const elements = modal.querySelectorAll('div, li, p, span');
                    for (const el of elements) {
                        if (el.textContent.trim().toLowerCase() === category || el.textContent.trim().toLowerCase() === category + 's') {
                            const parent = el.closest('div[class*="item"], li, tr, div') || el.parentElement;
                            if (parent) {
                                const btns = parent.querySelectorAll('button');
                                for (const btn of btns) {
                                    // STRICT check: text must be exactly '+' or '＋', NEVER .includes('+')
                                    const text = btn.textContent.trim();
                                    if ((text === '+' || text === '＋') && btn.offsetParent !== null && !btn.disabled) {
                                        return btn;
                                    }
                                }
                            }
                        }
                    }
                    return null;
                }

                function getMinusButton(category) {
                    const selectors = [
                        `button[data-selenium="occupancy-${category}-minus"]`,
                        `button[data-selenium="occupancy-${category}-decrease"]`,
                        `button[data-element-name="occupancy-${category}-decrease"]`,
                        `button[data-element-name="occupancy-${category}-minus"]`,
                        `button[aria-label*="Decrease ${category}" i]`,
                        `button[aria-label*="Remove ${category}" i]`
                    ];
                    for (const sel of selectors) {
                        const btn = modal.querySelector(sel);
                        if (btn && btn.offsetParent !== null && !btn.disabled) return btn;
                    }
                    return null;
                }

                function clickCount(btn, count, label) {
                    if (!btn || count <= 0) return 0;
                    let clicked = 0;
                    for (let i = 0; i < count; i++) {
                        if (btn.disabled || btn.offsetParent === null) break;
                        btn.click();
                        clicked++;
                    }
                    log.push(`Clicked ${label} ${clicked} times.`);
                    return clicked;
                }

                if (adultMinus > 0) {
                    const btn = getMinusButton('adult');
                    clickCount(btn, adultMinus, 'adult minus');
                }

                clickCount(getPlusButton('adult'), adultPlus, 'adult plus');
                clickCount(getPlusButton('child') || getPlusButton('children'), childPlus, 'child plus');
                clickCount(getPlusButton('room'), roomPlus, 'room plus');

                return { success: true, log };
            }
            """,
            {
                "adultPlus": adult_clicks_needed,
                "adultMinus": adult_minus_needed,
                "childPlus": child_clicks_needed,
                "roomPlus": room_clicks_needed
            }
        )

        for msg in adjust_result.get('log', []):
            print(f"  {msg}")

        await self.page.wait_for_timeout(300)

        # 6. Click the Search button
        print("🔍 Clicking Search button...")
        search_clicked = await self.page.evaluate("""
            () => {
                // 1. Target Agoda's standard search button selectors
                const searchSelectors = [
                    'button[data-selenium="searchButton"]',
                    'button[data-element-name="search-button"]',
                    'button[data-cy="search-button"]',
                    'button[data-testid="search-button"]',
                    'button[data-testid="hotel-search-button"]',
                    'button[data-selenium="search-box-search-button"]'
                ];

                for (const sel of searchSelectors) {
                    const btn = document.querySelector(sel);
                    if (btn && btn.offsetParent !== null && !btn.disabled) {
                        btn.click();
                        return { clicked: true, method: sel };
                    }
                }

                // 2. Fallback: Find button with text containing "SEARCH"
                const buttons = [...document.querySelectorAll('button')];
                for (const btn of buttons) {
                    const text = btn.textContent.trim().toUpperCase();
                    if ((text.includes('SEARCH') || text.includes('SEARCH HOTELS')) && 
                        !text.includes('FLIGHT') && 
                        btn.offsetParent !== null && 
                        !btn.disabled) {
                        btn.click();
                        return { clicked: true, method: 'text: ' + text };
                    }
                }
                return { clicked: false };
            }
        """)

        if not search_clicked.get("clicked"):
            fallback_btn = self.page.locator(
                'button[data-selenium="searchButton"], '
                'button:has-text("SEARCH"), '
                'button:has-text("Search")'
            ).first
            if await fallback_btn.count() > 0 and await fallback_btn.is_visible():
                await fallback_btn.click()
                print("✅ Clicked search button using Playwright locator.")
            else:
                raise Exception("Could not find or click the Agoda Search button.")
        else:
            print(f"✅ Search button clicked via {search_clicked.get('method')}.")

        # 7. Wait for results page to load
        try:
            await self.page.wait_for_selector(
                "div[data-selenium='hotel-item'], div[data-testid='property-card'], ol.hotel-list-container li",
                timeout=15000
            )
        except Exception:
            print("⚠️ Timeout waiting for hotel cards; proceeding with current DOM.")

                # 7. Wait for results page to load
        await self.page.wait_for_load_state("networkidle", timeout=35000)
        await self.page.screenshot(path="agoda_search_results.png", full_page=True)
        print("📸 Screenshot saved as agoda_search_results.png")

        # 8. Scrape hotel cards using stable selectors
        print("🔍 Scraping hotel cards with stable selectors...")

        # Primary card selector (from your inspection)
        card_selector = 'li[data-selenium="hotel-item"]'
        cards = self.page.locator(card_selector)
        card_count = await cards.count()

        if card_count == 0:
            # Fallback: try alternative selectors
            print("⚠️ No cards with 'li[data-selenium=\"hotel-item\"]'. Trying alternatives...")
            alt_selectors = ['div[data-testid="property-card"]', 'div[data-selenium="hotel-item"]']
            for sel in alt_selectors:
                cards = self.page.locator(sel)
                card_count = await cards.count()
                if card_count > 0:
                    print(f"✅ Found {card_count} cards using '{sel}'.")
                    break
            if card_count == 0:
                await self.page.screenshot(path="agoda_no_cards.png")
                print("📸 No cards found. Saved agoda_no_cards.png")
                return []

        print(f"🔍 Found {card_count} card elements.")
        # --- After finding cards, scroll through the list first to force lazy content to mount ---
        for _ in range(8):
            await self.page.mouse.wheel(0, 1200)
            await self.page.wait_for_timeout(1200)
        await self.page.wait_for_timeout(1200)
        # Scroll back up so element positions are stable for the loop below
        await self.page.evaluate("window.scrollTo(0, 0)")
        await self.page.wait_for_timeout(300)
        
        
        
        
        


        hotels = []
        for i in range(min(card_count, limit * 3)):
            if len(hotels) >= limit:
         
                break
            card = cards.nth(i)

            # 1. Hotel name — target the title anchor directly, not the whole header
            name_el = card.locator('a[data-element-name="ssr-property-card-title"]')
            
            name = ''
            if await name_el.count() > 0:
                raw_name = await name_el.inner_text()
                name = raw_name.strip()
            else:
                try:
                    card_html = await card.inner_html()
                    print(f"card {i} html:\n{card_html[:2000]}")
                except Exception as e:
                    print(f"⚠️ Could not fetch card {i} HTML either: {e}")
                continue

            if not name or len(name) < 3:
                print(f"no name found")
                continue

            # 2. Distance — separate, targeted element instead of parsing header blob
            distance = ''
            dist_el = card.locator('[data-selenium="distance"], span:has-text("km from"), span:has-text("to center")').first
            if await dist_el.count() > 0:
                dist_text = await dist_el.inner_text()
                dist_match = re.search(r'(\d+\.?\d*)\s*km', dist_text, re.I)
                if dist_match:
                    distance = dist_match.group(0)

            price_el = card.locator('[data-selenium="display-price"]')
            price = None
            is_sold_out = False
            try:
                await price_el.first.wait_for(timeout=2500, state="attached")
                price_raw = await price_el.first.inner_text()
                match = re.search(r'\d[\d,]*', price_raw)
                price = float(match.group().replace(',', '')) if match else None
            except Exception:
                # Check if this is a genuine "sold out" case rather than a scraping failure
                sold_out_text = card.locator('text=/Sold out/i')
                if await sold_out_text.count() > 0:
                    is_sold_out = True
                    print(f"🚫 '{name}' is sold out for these dates — skipping.")
                else:
                    print(f"❌ DEBUG: Price not found for '{name}' — unknown reason, not sold-out.")

            if is_sold_out:
                continue  # don't add sold-out hotels to results
                

            # 3. Rating – use the review container (no strict mode)
            review_container = card.locator('[data-element-name="property-card-review"]')
            rating = None
            if await review_container.count() > 0:
                review_text = await review_container.text_content()
                if review_text:
                    # Extract rating from text like "Average rating Excellent 8.0 out of 10 with 1,009 reviews"
                    match = re.search(r'(\d+\.?\d*)\s*(?:out of|Excellent|Very Good|Good)', review_text, re.I)
                    if match:
                        rating = float(match.group(1))

            # 4. Detail URL
            link_el = card.locator('a').first
            detail_url = await link_el.get_attribute('href') if await link_el.count() > 0 else None
            if detail_url and not detail_url.startswith('http'):
                detail_url = 'https://www.agoda.com' + detail_url

            hotel_id = detail_url.split('/')[-2] if detail_url else f'agoda-{i}'

            # 5. Filter out non-hotel properties
            full_text = await card.inner_text()
            if re.search(r'(Entire home|Private room|Homes & Apts)', full_text, re.I):
                print(f"⏭️ Skipping non-hotel: {name}")
                continue

            hotels.append(
                Hotel(
                    id=hotel_id,
                    name=name,
                    source="Agoda",
                    rating=rating,
                    price_per_night=price,
                    address=destination,
                    detail_url=detail_url,
                )
            )
            print(f"🏨 Found: {name} — ₹{price} — rating {rating} (distance: {distance})")

        print(f"🏨 Scraped {len(hotels)} hotels from Agoda.")
        return hotels
    
    # ------------------- Helper methods -------------------
    async def _select_date_agoda(self, date_obj: datetime):
        day = date_obj.day
        date_str = date_obj.strftime("%Y-%m-%d")

        try:
            await self.page.wait_for_selector(
                '.DayPicker, .calendar, [role="grid"], div[data-selenium="calendar-wrapper"]',
                timeout=5000
            )
        except Exception:
            raise Exception("Date picker did not appear on the page.")

        result = await self.page.evaluate(
            """
            (args) => {
                const dateStr = args.dateStr;
                const day = args.day;

                const byData = document.querySelector(
                    `td[data-selenium="date-${dateStr}"] button, div[data-date="${dateStr}"], span[data-date="${dateStr}"]`
                );
                if (byData) {
                    byData.click();
                    return "data";
                }

                const byAria = document.querySelector(`[aria-label*="${dateStr}"]`);
                if (byAria) {
                    byAria.click();
                    return "aria";
                }

                const elements = document.querySelectorAll('button, td[role="gridcell"], div[role="gridcell"]');
                for (const el of elements) {
                    if (el.textContent.trim() === String(day) && 
                        el.offsetParent !== null && 
                        !el.disabled) {
                        el.click();
                        return "fallback";
                    }
                }
                return false;
            }
            """,
            {"dateStr": date_str, "day": day}
        )

        if not result:
            raise Exception(f"Could not select date {date_str} on Agoda.")
        await self.page.wait_for_timeout(400)

    async def _kill_popups(self, selectors: Optional[list] = None):
        """Close overlays, cookie banners, and discount popups."""
        popup_selectors = [
            "button[aria-label='Close']",
            "button[data-selenium='popup-close']",
            "div[class*='modal'] button.close",
            "button:has-text('×')",
            "button:has-text('OK')",
            "button:has-text('Accept')"
        ]
        for sel in popup_selectors:
            try:
                locator = self.page.locator(sel)
                if await locator.count() > 0 and await locator.first.is_visible():
                    await locator.first.click()
                    await self.page.wait_for_timeout(300)
            except Exception:
                pass

    async def book_hotel(self, hotel: Hotel, room_choice: Optional[str] = None) -> dict:
        if not hotel.detail_url:
            raise BookingError("No detail URL available for Agoda hotel. Please re-run the search.")
        await self.page.goto(hotel.detail_url, wait_until="domcontentloaded", timeout=30000)
        return {
            "cart_items": "Agoda booking flow placeholder.",
            "total_cost": 0,
            "packs_added": 0,
            "page_url": self.page.url,
        }