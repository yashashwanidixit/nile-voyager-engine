import re
from pathlib import Path
from typing import Optional, List
from playwright.async_api import async_playwright

from app.models import Hotel

class SessionExpiredError(Exception):
    pass

class BookingError(Exception):
    pass

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
VIEWPORT = {"width": 1366, "height": 900}


class HotelSession:
    """Base class for platform‑specific scrapers using a storage_state JSON file."""

    def __init__(self, platform: str):
        self.platform = platform
        self.state_file = Path(f"{platform}_auth_state.json")
        if not self.state_file.exists():
            raise FileNotFoundError(
                f"Session file {self.state_file} not found. "
                f"Run capture_session.py --platform {platform} first."
            )

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        browser = await self.playwright.chromium.launch(headless=False)  # set to True later
        self.context = await browser.new_context(
            storage_state=str(self.state_file),
            user_agent=USER_AGENT,
            viewport=VIEWPORT,
            locale="en-IN",
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

    # --- Abstract methods ---
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

    async def _ensure_logged_in(self):
        """Check if we are still logged in; raise SessionExpiredError if not."""
        # First check URL for login patterns
        if "signin" in self.page.url.lower() or "login" in self.page.url.lower():
            raise SessionExpiredError(f"{self.platform} redirected to login.")

        if self.platform == "mmt":
            if await self.page.locator("button:has-text('Login')").count() > 0:
                raise SessionExpiredError("MMT session expired.")
        elif self.platform == "booking":
            if await self.page.locator("a:has-text('Sign in')").count() > 0:
                raise SessionExpiredError("Booking session expired.")
        elif self.platform == "agoda":
            # Use both URL and element checks
            login_selectors = [
                "button[data-selenium='signinButton']",
                "a:has-text('Sign in')",
                "a:has-text('Log in')",
                "a[data-selenium='signinLink']",
                "button:has-text('Sign in')",
                "div[data-selenium='userMenu'] button"
            ]
            for sel in login_selectors:
                if await self.page.locator(sel).count() > 0:
                    raise SessionExpiredError("Agoda session expired (sign-in button visible).")

            # Look for a user profile element (indicates logged in)
            profile_selectors = [
                "div[data-selenium='userProfile']",
                "a[data-selenium='myAccountLink']",
                "div[data-testid='user-avatar']",
                "button[data-testid='user-menu-button']"
            ]
            logged_in = False
            for sel in profile_selectors:
                if await self.page.locator(sel).count() > 0:
                    logged_in = True
                    break
            if not logged_in:
                raise SessionExpiredError("Agoda session expired (no user profile found).")