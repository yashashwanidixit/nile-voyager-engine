import asyncio
import sys
import argparse
from playwright.async_api import async_playwright

PLATFORMS = {
    "mmt": "https://www.makemytrip.com/",
    "agoda": "https://www.agoda.com/",
    "booking": "https://www.booking.com/"
}

async def capture_platform(platform: str, url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-http2", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context()
        page = await context.new_page()

        # Block resource types that aren't critical for login
        await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "stylesheet", "font", "media"] else route.continue_())

        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        # Now you can log in manually – the page should be usable

        print("\n" + "=" * 60)
        print(f"Browser opened for {platform.upper()}.")
        print("1. Log in manually (Google, email, OTP, etc.).")
        print("2. Once you see the home page / search is available, come back here.")
        print("3. Press ENTER to save the session.")
        print("=" * 60 + "\n")

        input("Press ENTER when logged in... ")

        await context.storage_state(path=state_file)
        print(f"Session saved to {state_file}.\n")
        await browser.close()

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=PLATFORMS.keys(),
                        help="Capture only this platform (if omitted, captures all)")
    args = parser.parse_args()

    if args.platform:
        # Capture only the specified platform
        await capture_platform(args.platform, PLATFORMS[args.platform])
    else:
        # Capture all platforms sequentially
        for platform, url in PLATFORMS.items():
            await capture_platform(platform, url)
        print("\n✅ All sessions captured successfully!")

if __name__ == "__main__":
    asyncio.run(main())