from pathlib import Path
from typing import Optional, List
from playwright.async_api import async_playwright

from app.models import Hotel



class HotelSession:
    """Base class for platform‑specific scrapers using saved auth state."""

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
        browser = await self.playwright.chromium.launch(headless=False)  # visible
        self.context = await browser.new_context(storage_state=str(self.state_file))
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

    # --- Helpers (can be used by subclasses) ---
    async def _safe_text(self, locator):
        try:
            return (await locator.text_content()).strip()
        except:
            return ""

    async def _kill_popups(self, selectors: list):
        """Click any popup close buttons that appear."""
        for sel in selectors:
            try:
                if await self.page.locator(sel).count() > 0:
                    await self.page.locator(sel).first.click()
                    await self.page.wait_for_timeout(500)
                    break
            except Exception:
                pass

    async def _extract_total_price(self, selector: str) -> float:
        """Extract a numeric price from a given selector."""
        import re
        txt = await self._safe_text(self.page.locator(selector))
        nums = re.findall(r'[\d,]+\.?\d*', txt.replace(',', ''))
        return float(nums[0]) if nums else 0.0