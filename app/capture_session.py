import asyncio
import argparse
from playwright.async_api import async_playwright

PLATFORMS = {
    "mmt": "https://www.makemytrip.com/",
    "agoda": "https://www.agoda.com/",
    "booking": "https://www.booking.com/"
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
VIEWPORT = {"width": 1366, "height": 900}

async def capture_platform(platform: str, url: str):
    user_data_dir = f"./{platform}_profile"   # folder to store full profile
    print(f"\n=== Capturing session for {platform.upper()} ===")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            viewport=VIEWPORT,
            user_agent=USER_AGENT,
            locale="en-IN",
        )
        page = await context.new_page()
        await page.goto(url)

        print("\n" + "=" * 60)
        print(f"Browser opened for {platform.upper()}.")
        print("1. Log in manually (complete all steps, including any 2FA/passkey).")
        print("2. After login, navigate to the search page (e.g., hotels search) and wait a few seconds.")
        print("3. Press ENTER to save the session.")
        print("=" * 60 + "\n")

        input("Press ENTER when fully logged in... ")

        # Optional: perform a dummy search to load additional session data
        if platform == "booking":
            await page.goto("https://www.booking.com/searchresults.html?ss=Paris")
        elif platform == "agoda":
            await page.goto("https://www.agoda.com/search?city=1")
        elif platform == "mmt":
            await page.goto("https://www.makemytrip.com/hotels/")

        await page.wait_for_timeout(3000)  # let cookies/session settle
        await context.close()  # auto‑saves everything to user_data_dir
        print(f"Session profile saved to {user_data_dir}.\n")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=PLATFORMS.keys(),
                        help="Capture only this platform (if omitted, captures all)")
    args = parser.parse_args()

    if args.platform:
        await capture_platform(args.platform, PLATFORMS[args.platform])
    else:
        for platform, url in PLATFORMS.items():
            await capture_platform(platform, url)
        print("\n✅ All sessions captured successfully!")

if __name__ == "__main__":
    asyncio.run(main())