"""
Shared Playwright setup for all site scrapers.

Why Playwright instead of the accessibility-service approach:
- Runs headless on a server -> no dependency on a specific phone's DOM/accessibility tree.
- Same script works whether you later call it from a backend, a cron job, or a CI runner.
- Can wait on network/JS state explicitly instead of guessing with sleeps.

IMPORTANT: MakeMyTrip / Agoda / Booking.com change their DOM frequently and have
anti-bot protections. The CSS/XPath selectors in the scraper files are illustrative
starting points based on typical structure - open devtools on the live site and
update the selectors marked with "# VERIFY SELECTOR" before relying on this in prod.
For a more durable stage-3 solution, prefer official partner/affiliate APIs
(Booking.com Affiliate Partner API, Agoda Partner API) over DOM scraping wherever
you can get access - they return structured JSON and won't break on a CSS change.
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright

# ============================================================
# CHANGE 1: Global Windows Event Loop Fix
# This prevents the "NotImplementedError" crash on Windows 
# for any scraper that imports and uses `new_page`.
# ============================================================
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@asynccontextmanager
async def new_page(headless: bool = False):
    """Yields a ready-to-use Playwright page with sane defaults."""
    async with async_playwright() as pw:
        # ============================================================
        # CHANGE 2: Added `slow_mo=100`
        # Slows down actions by 100ms per step. Greatly reduces the 
        # chance of getting flagged as a bot / hitting a CAPTCHA.
        # ============================================================
        browser = await pw.chromium.launch(
            headless=headless, 
            slow_mo=100,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="en-IN",
        )
        page = await context.new_page()
        try:
            yield page
        finally:
            await context.close()
            await browser.close()


async def safe_text(locator) -> str:
    """Returns stripped text content, or '' if the element isn't found."""
    try:
        if await locator.count() == 0:
            return ""
        return (await locator.first.inner_text()).strip()
    except Exception:
        return ""


def parse_price(raw: str) -> float:
    """'₹4,599' / 'INR 4599' -> 4599.0"""
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0


def parse_rating(raw: str) -> float:
    """Handles '4.3', '4.3/5', '4.3 Very Good' -> 4.3. Returns 0.0 if unparseable."""
    import re
    match = re.search(r"\d(\.\d)?", raw)
    return float(match.group()) if match else 0.0