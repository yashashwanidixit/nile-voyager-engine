



import asyncio
import sys

from app.models import Hotel
from app.profiles import get_profile
from app.ranking import select_top_hotels
from app.scrapers.makemytrip import MakeMyTripSession, SessionExpiredError
from app.scrapers.agoda import AgodaSession
from app.scrapers.booking import BookingSession



async def scrape_platform(platform_class, platform_name, destination, checkin, checkout,
                          adults, children, rooms, limit=5):
    """Helper to scrape a single platform and handle errors."""
    try:
        async with platform_class() as session:
            hotels = await session.search_hotels(
                destination, checkin, checkout,
                adults=adults, children=children, rooms=rooms, limit=limit
            )
            return platform_name, hotels
    except FileNotFoundError as e:
        print(f"⚠️  {platform_name} session missing: {e}")
        return platform_name, []
    except SessionExpiredError as e:
        print(f"⚠️  {platform_name} session expired: {e}")
        return platform_name, []
    except Exception as e:
        print(f"⚠️  {platform_name} error: {e}")
        return platform_name, []

async def main():
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  🏨 TRAVEL ASSISTANT — Hotel Booker")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # 1. Gather user input
    destination = input("Where are you going? → ").strip()
    if not destination:
        return
    checkin = input("Check-in (YYYY-MM-DD) → ").strip()
    checkout = input("Check-out (YYYY-MM-DD) → ").strip()
    adults = int(input("Adults → ") or "2")
    children = int(input("Children → ") or "0")
    rooms = int(input("Rooms → ") or "1")

    # 2. Load profile
    profile_id = input("Profile ID (default) → ") or "default"
    try:
        profile = get_profile(profile_id)
    except ValueError:
        print(f"Profile '{profile_id}' not found. Using default.")
        profile = get_profile("default")

    print("\n🔍 Searching all platforms (MakeMyTrip, Agoda, Booking.com)...")
    # 3. Scrape concurrently
    tasks = [
        scrape_platform(MakeMyTripSession, "MakeMyTrip", destination, checkin, checkout,
                        adults, children, rooms, limit=5),
        scrape_platform(AgodaSession, "Agoda", destination, checkin, checkout,
                        adults, children, rooms, limit=5),
        scrape_platform(BookingSession, "Booking.com", destination, checkin, checkout,
                        adults, children, rooms, limit=5),
    ]
    results = await asyncio.gather(*tasks)
    hotels_by_source = {name: hotels for name, hotels in results if hotels}

    if not hotels_by_source:
        print("No hotels found on any platform. Try a different search.")
        return

    # 4. Rank and display
    ranked = select_top_hotels(hotels_by_source, profile, per_source=5)
    print(f"\n🏨 Found {len(ranked)} top recommendations (ranked for your profile):\n")
    for i, hotel in enumerate(ranked, 1):
        print(f"  [{i}] {hotel.name} — ₹{hotel.price_per_night}/night — {hotel.rating or 'N/A'}⭐")
        print(f"      Source: {hotel.source}, Address: {hotel.address}\n")

    print("Type a number to select, or 0 to cancel.")
    try:
        choice = int(input("\nYour choice → ").strip())
    except ValueError:
        print("Invalid input.")
        return
    if choice == 0:
        print("Cancelled.")
        return
    if choice < 1 or choice > len(ranked):
        print("Invalid option.")
        return

    selected = ranked[choice - 1]

    # 5. Confirm selection
    print(f"\n┌─ Booking Confirmation ───────────────────────────────")
    print(f"│  Hotel   : {selected.name}")
    print(f"│  Price   : ₹{selected.price_per_night} per night")
    print(f"│  Source  : {selected.source}")
    print(f"└───────────────────────────────────────────────────────\n")

    if input("Proceed to book? (yes/no) → ").strip().lower() not in ("yes", "y"):
        print("Cancelled.")
        return

    # 6. Book – use the appropriate session class
    platform_map = {
        "MakeMyTrip": MakeMyTripSession,
        "Agoda": AgodaSession,
        "Booking.com": BookingSession,
    }
    session_cls = platform_map.get(selected.source)
    if not session_cls:
        print(f"Unknown source {selected.source}. Cannot book.")
        return

    print("\n🌐 Opening browser to book...")
    try:
        async with session_cls() as session:
            booking_info = await session.book_hotel(selected)   # pass the Hotel object
            print(f"\n✅ Added to cart. Total: ₹{booking_info['total_cost']}")
            print(f"📄 Checkout page: {booking_info['page_url']}")
            print("\n⏳ Please fill in guest details manually in the browser.")
            input("Press ENTER when done (or to cancel) → ")
    except Exception as e:
        print(f"\n❌ Booking error: {e}")

    print("\n👋 Thanks for using Travel Assistant!")

if __name__ == "__main__":
    asyncio.run(main())