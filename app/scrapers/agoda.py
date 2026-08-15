import asyncio
import re
from typing import List, Optional
from datetime import datetime

from app.scrapers.hotel_scraper_base import HotelSession, SessionExpiredError, BookingError
from app.models import Hotel
from app.scrapers.base import parse_price, parse_rating


class AgodaSession(HotelSession):
    def __init__(self):
        super().__init__("agoda")  # IMPORTANT: use "agoda", not "mmt"

    async def search_hotels(self, destination: str, checkin: str, checkout: str,
                            adults: int = 2, children: int = 0, rooms: int = 1,
                            limit: int = 5) -> List[Hotel]:
        # 1. Go to Agoda homepage (use self.page from base class)
        await self.page.goto("https://www.agoda.com/", wait_until="domcontentloaded")
        await self._kill_popups() # custom popup selectors
        # Use Playwright to find and click the Hotels tab
       # 1.5 Ensure we are on the Hotels tab
        # 1.5 Ensure we are on the Hotels tab
        # 1.5 Ensure we are on the Hotels tab (click it anyway)
        # 1.5 Ensure we are on the Hotels tab (click it anyway)
        print("🔍 Clicking Hotels tab...")

        try:
            # Use a CSS selector that matches the tab button with role="tab" and text "Hotels"
            tab_selector = 'button[role="tab"]:has-text("Hotels")'
            await self.page.wait_for_selector(tab_selector, state="visible", timeout=10000)
            hotels_tab = self.page.locator(tab_selector).first
            await hotels_tab.click()
            print("  ✅ Clicked Hotels tab using CSS selector.")
        except Exception as e:
            print(f"  ⚠️ CSS selector failed: {e}. Trying fallback...")
            try:
                # Fallback: use Playwright's role-based locator
                hotels_tab = self.page.get_by_role("tab", name="Hotels")
                await hotels_tab.first.wait_for(state="visible", timeout=5000)
                await hotels_tab.first.click()
                print("  ✅ Clicked Hotels tab using role fallback.")
            except Exception as e2:
                print(f"  ❌ Fallback also failed: {e2}")
                # Debug: save screenshot and HTML
                await self.page.screenshot(path="agoda_no_hotels_tab.png")
                html = await self.page.content()
                with open("agoda_page.html", "w", encoding="utf-8") as f:
                    f.write(html)
                raise Exception("Could not click Hotels tab. Check saved debug files.")

        await self.page.wait_for_timeout(1000)  # wait for the tab switch to take effectt
                

        # 2. Fill destination (Agoda's search input)
        dest_input = self.page.locator(
            "input[placeholder*='Enter a destination'], "
            "input[data-cy='hotelCitySearch'], "
            "input[aria-label='Search']"
        )
        dest_input = self.page.locator(
                "input[placeholder*='Enter a destination'], "
                "input[data-cy='hotelCitySearch'], "
                "input[aria-label='Search']"
)
        await dest_input.fill(destination)
        await self.page.wait_for_timeout(800)  # wait for the list to appear

        # Use JavaScript to find and click the first suggestion
        clicked = await self.page.evaluate("""
    (destination) => {
        const selectors = [
            'ul[data-selenium="autocomplete-result"] li',
            'div[role="listbox"] > div, div[role="listbox"] > li',
            'li[role="option"], div[role="option"]',
            'ul[class*="autocomplete"] li, div[class*="autocomplete"] li',
            'div[data-testid*="autocomplete"] li, div[data-automation*="autocomplete"] li'
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
        const containers = document.querySelectorAll('[role="listbox"], [data-selenium*="autocomplete"], [class*="autocomplete"]');
        for (const container of containers) {
            const firstChild = container.querySelector('li, div[role="option"]');
            if (firstChild && firstChild.textContent.trim().toLowerCase().includes(destination.toLowerCase())) {
                firstChild.click();
                return true;
            }
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
            
      
    
        

        # 4. Set dates – Agoda uses a different date picker
        checkin_date = datetime.strptime(checkin, "%Y-%m-%d")
        checkout_date = datetime.strptime(checkout, "%Y-%m-%d")

      
        await self._select_date_agoda(checkin_date)

        # Click the check-out field
        
        await self._select_date_agoda(checkout_date)

        # 5. Set guests (Agoda uses a dropdown)
        guest_opened = await self.page.evaluate("""
        () => {
            // 1. Check if already open
            const openPicker = document.querySelector('[role="dialog"][aria-label*="guests"], div[class*="guestPickerOpen"]');
            if (openPicker) {
                return "already_open";
            }

            // 2. Try standard CSS selectors (no :has-text)
            const selectors = [
                'button[data-selenium="guestPicker"]',
                'button[aria-label*="guests"]',
                'button[data-testid="guest-picker"]',
                'div[data-selenium="guestPicker"] button'
            ];
            for (const sel of selectors) {
                const btn = document.querySelector(sel);
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    return "clicked";
                }
            }

            // 3. Fallback: find any visible button that contains "Guests" in text
            const allButtons = document.querySelectorAll('button');
            for (const btn of allButtons) {
                const text = btn.textContent.trim().toLowerCase();
                if (text.includes('guests') && btn.offsetParent !== null) {
                    btn.click();
                    return "clicked_text";
                }
            }

            // 4. Last resort: press Tab
            const event = new KeyboardEvent('keydown', { key: 'Tab' });
            document.dispatchEvent(event);
            return "tab";
        }
    """)
        # Function to safely click a plus button if visible
        async def click_plus_button(selector, label, times=1):
            button = self.page.locator(selector)
            for _ in range(times):
                if await button.count() > 0 and await button.is_visible():
                    await button.click()
                    print(f"clicked{label} button {times} times")
                    await self.page.wait_for_timeout(200)
                else:
                    print(f"⚠️ {label} plus button not visible or not found.")
                    break

        print(f"DEBUG: adults={adults}, children={children}, rooms={rooms}")

# Compute the number of clicks needed
        adult_clicks_needed = max(0, adults - 1)   # default is 2
        child_clicks_needed = children             # default is 0
        room_clicks_needed = max(0, rooms - 1)     # default is 1

        print(f"🔧 Clicks needed: Adult={adult_clicks_needed}, Child={child_clicks_needed}, Room={room_clicks_needed}")

        # If no clicks needed, skip the whole JS call
        if adult_clicks_needed == 0 and child_clicks_needed == 0 and room_clicks_needed == 0:
            print("ℹ️ No guest adjustments needed.")
        else:
            # Run JavaScript to adjust guests and return detailed logs
            result = await self.page.evaluate(
                """
                (config) => {
                    const { adultClicks, childClicks, roomClicks } = config;
                    const log = [];

                    // Helper: find a button by text content within a container
                    function findButtonByText(container, text) {
                        const btns = container.querySelectorAll('button');
                        for (const btn of btns) {
                            if (btn.textContent.includes(text) && btn.offsetParent !== null && !btn.disabled) {
                                return btn;
                            }
                        }
                        return null;
                    }

                    // Helper: find plus button for a category
                    function findPlusButton(category) {
                        const categories = [category, category + 's'];
                        // 1. Try aria-label with "Increase" or "Add"
                        for (const name of categories) {
                            const btn = document.querySelector(`button[aria-label*="Increase ${name}"]`);
                            if (btn && btn.offsetParent !== null) return btn;
                            const btnAdd = document.querySelector(`button[aria-label*="Add ${name}"]`);
                            if (btnAdd && btnAdd.offsetParent !== null) return btnAdd;
                        }
                        // 2. Look for label text, then find '+' button nearby
                        const labels = document.querySelectorAll('label, span, div');
                        for (const label of labels) {
                            const text = label.textContent.trim().toLowerCase();
                            if (categories.some(c => text.includes(c))) {
                                const container = label.closest('div, li, section') || label.parentElement;
                                if (container) {
                                    const plusBtn = findButtonByText(container, '+');
                                    if (plusBtn) return plusBtn;
                                    const ariaBtn = container.querySelector('button[aria-label*="increase"]');
                                    if (ariaBtn && ariaBtn.offsetParent !== null) return ariaBtn;
                                }
                            }
                        }
                        // 3. Fallback: find any visible '+' button near category text
                        const allButtons = document.querySelectorAll('button');
                        for (const btn of allButtons) {
                            if (btn.textContent.includes('+') && btn.offsetParent !== null) {
                                const parent = btn.closest('div, li') || btn.parentElement;
                                if (parent && parent.textContent.toLowerCase().includes(category.toLowerCase())) {
                                    return btn;
                                }
                            }
                        }
                        return null;
                    }

                    // Click a plus button a number of times
                    function clickPlusButton(category, times) {
                        const startLog = log.length;
                        if (times <= 0) {
                            log.push(`ℹ️ No clicks needed for ${category}.`);
                            return 0;
                        }
                        const btn = findPlusButton(category);
                        if (!btn) {
                            log.push(`❌ Could not find plus button for ${category}.`);
                            return 0;
                        }
                        log.push(`✅ Found plus button for ${category}.`);
                        let clicked = 0;
                        for (let i = 0; i < times; i++) {
                            if (btn.offsetParent === null || btn.disabled) {
                                log.push(`⚠️ Button for ${category} became invisible/disabled after ${clicked} clicks.`);
                                break;
                            }
                            btn.click();
                            clicked++;
                            log.push(`   Clicked ${category} plus (${clicked}/${times})`);
                        }
                        log.push(`📊 ${category} clicked ${clicked} times (expected ${times}).`);
                        return clicked;
                    }

                    const result = {
                        adultClicks: clickPlusButton('adult', adultClicks),
                        childClicks: clickPlusButton('child', childClicks),
                        roomClicks: clickPlusButton('room', roomClicks),
                        log: log
                    };
                    return result;
                }
                """,
                {
                    "adultClicks": adult_clicks_needed,
                    "childClicks": child_clicks_needed,
                    "roomClicks": room_clicks_needed
                }
            )

        # Print each log message from JavaScript
        print("\n📋 Guest adjustment log:")
        for msg in result['log']:
            print(f"  {msg}")

        # Print summary
        print(f"\n✅ Summary:")
        print(f"  Adult clicks: {result['adultClicks']} / {adult_clicks_needed}")
        print(f"  Child clicks: {result['childClicks']} / {child_clicks_needed}")
        print(f"  Room clicks:  {result['roomClicks']} / {room_clicks_needed}")

        # Check if all expected clicks were performed
        if (result['adultClicks'] != adult_clicks_needed or
            result['childClicks'] != child_clicks_needed or
            result['roomClicks'] != room_clicks_needed):
            print("⚠️ Some guest adjustments may have failed.")
        else:
            print("✅ All guest adjustments completed successfully.")

        await self.page.wait_for_timeout(500)
        


        # ... your existing code that fills destination, dates, guests ...
        print("✅ All guest adjustments completed successfully.")
        await self.page.screenshot(path="debug_after_hotels_click.png", full_page=True)
        print("Screenshot saved to debug_after_hotels_click.png")

        # --- NEW: verify we're actually on the Hotels-only form before searching ---
        state = await self.page.evaluate("""
            () => {
                const tabs = [...document.querySelectorAll('button')].filter(b =>
                    ['Hotels','Flights','Homes & Apts','Flight + Hotel','Activities','Airport transfer'].includes(b.textContent.trim())
                );
                const tabInfo = tabs.map(b => ({
                    text: b.textContent.trim(),
                    ariaSelected: b.getAttribute('aria-selected'),
                    ariaCurrent: b.getAttribute('aria-current')
                }));
                const hasFlightFields = !!document.querySelector('[data-selenium="flight-option-button"], [data-selenium="flight-cabin-class-button"]');
                return { tabInfo, hasFlightFields };
            }
        """)
        print(state)

        if state['hasFlightFields']:
            print("⚠️ Still on combo Flight+Hotel form — re-clicking Hotels tab")
            await self.page.locator('button:has-text("Hotels")').click()
            await self.page.wait_for_timeout(1000)  # or better: wait_for_selector to confirm flight fields are gone
            
        # Screenshot right after the click (catches the in-between/empty state)
       

        # --- then proceed to your existing search-click code ---
        result = await self.page.evaluate("""
        () => {
            const log = [];
            const buttons = [...document.querySelectorAll('button')];
            log.push(`Found ${buttons.length} total buttons on page.`);

            for (const btn of buttons) {
                const text = btn.textContent.trim().toLowerCase();
                if (text === 'search' && btn.offsetParent !== null && !btn.disabled) {
                    btn.click();
                    log.push('Clicked button with exact text "search".');
                    return { success: true, log };
                }
            }

            return { success: false, log };
        }
    """)

        for msg in result['log']:
            print(f"  {msg}")

        if not result['success']:
            raise Exception("Could not find Search button.")
        else:
            print("✅ Search initiated.")
       
        # 8. Scrape hotel cards
        cards = self.page.locator("div[data-selenium='hotel-item'], div[data-testid='property-card']")
        count = min(await cards.count(), limit * 3)
        hotels = []
        for i in range(count):
            if len(hotels) >= limit:
                break
            card = cards.nth(i)
            name = await self._safe_text(card.locator("[data-selenium='hotel-name'], [data-testid='title']"))
            rating_raw = await self._safe_text(card.locator("[data-selenium='rating'], [data-testid='review-score']"))
            price_raw = await self._safe_text(card.locator("[data-selenium='price'], [data-testid='price']"))
            if not name:
                continue

            # Extract detail URL
            link = await card.locator("a").first.get_attribute("href")
            detail_url = None
            if link:
                if not link.startswith("http"):
                    detail_url = "https://www.agoda.com" + link
                else:
                    detail_url = link

            hotel_id = detail_url.split('/')[-2] if detail_url else f"agoda-{i}"

            hotels.append(
                Hotel(
                    id=hotel_id,
                    name=name,
                    source="Agoda",
                    rating=parse_rating(rating_raw),
                    price_per_night=parse_price(price_raw),
                    address=destination,
                    detail_url=detail_url,
                )
            )
        return hotels

    async def _select_date_agoda(self, date_obj: datetime):
        day = date_obj.day
        date_str = date_obj.strftime("%Y-%m-%d")

        # Wait for the date picker
        try:
            await self.page.wait_for_selector('.DayPicker, .calendar, [role="grid"]', timeout=5000)
        except:
            raise Exception("Date picker did not appear on the page.")

        # Pass a single object with both values
        result = await self.page.evaluate(
            """
            (args) => {
                const dateStr = args.dateStr;
                const day = args.day;
                // 1. Try data-selenium or data-date
                const byData = document.querySelector(
                    `td[data-selenium="date-${dateStr}"] button, div[data-date="${dateStr}"]`
                );
                if (byData) {
                    byData.click();
                    return "data";
                }
                // 2. Try aria-label
                const byAria = document.querySelector(`[aria-label*="${dateStr}"]`);
                if (byAria) {
                    byAria.click();
                    return "aria";
                }
                // 3. Fallback: find visible enabled day number
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
            {"dateStr": date_str, "day": day}   # one argument, a dict
        )

        if result == "data":
            print(f"✅ Selected date {day:02d} using data-selenium.")
        elif result == "aria":
            print(f"✅ Selected date {day:02d} using aria-label.")
        elif result == "fallback":
            print(f"✅ Selected date {day:02d} using fallback (day number).")
        else:
            raise Exception(f"Could not select date {day:02d} on Agoda.")
        await self.page.wait_for_timeout(500)

    async def _kill_popups(self):
        print("✅ Using Agoda-specific popup killer")
        """Override with Agoda-specific popup close selectors."""
        popup_selectors = [
            "button[aria-label='Close']",
            "button[data-selenium='popup-close']",
            "div[class*='modal'] button.close",
            "button:has-text('×')"
        ]
        for sel in popup_selectors:
            try:
                if await self.page.locator(sel).count() > 0:
                    await self.page.locator(sel).first.click()
                    await self.page.wait_for_timeout(500)
                    break
            except Exception:
                pass

    async def book_hotel(self, hotel: Hotel, room_choice: Optional[str] = None) -> dict:
        if not hotel.detail_url:
            raise BookingError("No detail URL available for Agoda hotel. Please re-run the search.")
        await self.page.goto(hotel.detail_url, wait_until="domcontentloaded", timeout=30000)
        # Agoda booking flow – you'll need to adapt selectors
        # For now, a placeholder:
        return {
            "cart_items": "Agoda booking flow not fully implemented yet.",
            "total_cost": 0,
            "packs_added": 0,
            "page_url": self.page.url,
        }

# Exceptions are already defined in base class – no need to redefine