from pathlib import Path
from typing import Optional, List
from playwright.async_api import async_playwright

from app.models import Hotel



class SessionExpiredError(Exception):
    """Raised when the saved session has expired."""
    pass

class BookingError(Exception):
    """Raised when booking fails."""
    pass
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
VIEWPORT = {"width": 1366, "height": 900}



class HotelSession:
    """Base class for platform‑specific scrapers using a persistent profile."""

    def __init__(self, platform: str):
        self.platform = platform
        self.profile_dir = Path(f"./{platform}_profile")
        if not self.profile_dir.exists():
            raise FileNotFoundError(
                f"Profile directory {self.profile_dir} not found. "
                f"Run capture_session.py --platform {platform} first."
            )

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            str(self.profile_dir),
            headless=False,                 # set to True later if you want
            viewport=VIEWPORT,
            user_agent=USER_AGENT,
            locale="en-IN",
            # Add extra headers to mimic a real browser
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Ch-Ua": '"Chromium";v="124", "Not.A/Brand";v="99"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            }
        )
        self.page = await self.context.new_page()
        return self

    async def __aexit__(self, *args):
        await self.context.close()
        await self.playwright.stop()

    # --- Methods to be overridden ---
    async def search_hotels(self, destination: str, checkin: str, checkout: str,
                            adults: int = 2, children: int = 0, rooms: int = 1,
                            limit: int = 5) -> List[Hotel]:
        raise NotImplementedError

    async def book_hotel(self, hotel: Hotel, room_choice: Optional[str] = None) -> dict:
        raise NotImplementedError

    # --- Helpers ---
    async def _safe_text(self, locator):
        try:
            return (await locator.text_content()).strip()
        except:
            return ""

    async def _kill_popups(self, selectors: list):
        for sel in selectors:
            try:
                if await self.page.locator(sel).count() > 0:
                    await self.page.locator(sel).first.click()
                    await self.page.wait_for_timeout(500)
                    break
            except Exception:
                pass

    async def _extract_total_price(self, selector: str) -> float:
        import re
        txt = await self._safe_text(self.page.locator(selector))
        nums = re.findall(r'[\d,]+\.?\d*', txt.replace(',', ''))
        return float(nums[0]) if nums else 0.0

    # Add a session expiry check
    async def _ensure_logged_in(self):
        if self.platform == "mmt":
            if await self.page.locator("button:has-text('Login')").count() > 0:
                raise SessionExpiredError("MMT session expired.")
        elif self.platform == "booking":
            if await self.page.locator("a:has-text('Sign in')").count() > 0:
                raise SessionExpiredError("Booking session expired.")
        elif self.platform == "agoda":
            if await self.page.locator("button[data-selenium='signinButton']").count() > 0:
                raise SessionExpiredError("Agoda session expired.")