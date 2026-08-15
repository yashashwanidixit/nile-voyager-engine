# Nile voyager engine— Stage 1

Recommends 15 hotels (top 5 each from MakeMyTrip, Agoda, Booking.com) filtered
by a hardcoded user rating-preference profile, with a reason per hotel. Once a
hotel is picked, recommends 5 Rapido ride options with a reason per ride.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

## Endpoints

`POST /hotels`
```json
{"profile_id": "user_5star", "destination": "Whitefield, Bangalore",
 "checkin": "20/08/2026", "checkout": "21/08/2026"}
```
Returns up to 15 hotels with `reason` fields explaining the selection.

`POST /rides`
```json
{"profile_id": "user_5star",
 "pickup_lat": 13.1986, "pickup_lon": 77.7066,
 "hotel_lat": 12.9698, "hotel_lon": 77.7500}
```
Returns 5 ride options (Bike/Auto/Cab Economy/Cab Premium) with reasons,
preferred vehicle type ranked first.

## Known limitations (by design, for stage 1)

- **Scraper selectors are illustrative**, marked `# VERIFY SELECTOR`. All
  three sites change DOM structure often and have anti-bot measures — open
  devtools on the live site and update selectors before depending on this.
  If a scrape returns nothing, the site likely changed or blocked the
  headless browser (check for a CAPTCHA/blocked-page redirect).
- **Rapido rides are estimated**, not live-scraped — there's no public
  consumer API, and their web flow is also session-gated. The fare formula
  in `rides.py` is a reasonable Bangalore-rate approximation for now.
- **No real booking happens.** This stage only recommends + explains.

## Stage 2 roadmap (recommended order)

1. **Add the distance factor** (do this first — deterministic, fast, no data
   needed): geocode the meeting address in Whitefield and each candidate
   hotel (Google Geocoding API or free Nominatim/OSM), rank within the
   rating band by distance/ETA instead of rating alone.
2. **Booking via deep link handoff**, not full automation: once the user
   picks a hotel/ride, open the site/app with prefilled search params and
   let the user complete payment. Don't retry the accessibility-service
   full-auto-booking approach — it's proven unreliable against MakeMyTrip's
   DOM and OTP/payment steps make full automation both fragile and
   ToS-risky.
3. **LLM-learned preference** — worth doing only after you have real usage
   data (which hotels/rides users actually pick vs. what was recommended).
   Not enough signal yet with 2 hardcoded profiles; revisit once the app has
   real users.
