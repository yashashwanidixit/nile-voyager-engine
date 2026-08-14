# What changed vs. the old Rapido-only pipeline

## New flow (matches your diagram)
`User input` → `geocoding.py` (Nominatim) → `routing.py` (GraphHopper, real
road distance + duration) → `rides.py` (fare estimator) → comparison screen
(`main.py` response) → `deeplinks.py` (handoff to the real app).

## Files touched
| File | What changed |
|---|---|
| `app/models.py` | `RideOption` now has `provider`, `is_preferred`, `deep_link`. New `PlatformRides` groups 3 options under one app. `UserProfile.preferred_ride_type` → `preferred_vehicle_type` (values now just `"Bike"/"Auto"/"Cab"`, not vehicle-type strings tied to one provider). |
| `app/geocoding.py` | **New.** Nominatim wrapper, with the required User-Agent header and a Bangalore viewbox bias so ambiguous names resolve locally. |
| `app/routing.py` | **New.** GraphHopper wrapper — replaces `haversine_km`. Straight-line distance was underselling real trip length/cost; this uses actual road distance + duration. |
| `app/rides.py` | Rewritten. One `RATE_CARD` per (provider × vehicle type) = 9 rate rows instead of 4. `estimate_all_platforms()` returns 3 `PlatformRides` (Uber/Ola/Rapido), each with Bike/Auto/Cab, the user's preferred type sorted first and flagged `is_preferred=True`. |
| `app/deeplinks.py` | **New.** Builds the real handoff URLs — see caveats below. |
| `app/profiles.py` | Field rename only (`preferred_vehicle_type`). |
| `app/main.py` | `/rides` now takes `pickup_text` / `drop_text` (free text) instead of raw lat/lon — geocodes both, routes, estimates, returns per-platform grouped results with deep links. `/hotels` untouched. |
| `app/ranking.py` | Unchanged — copied through as-is. |

## Price estimation — what's real, what isn't
No app here has a live-fare API a normal developer can call:
- **Uber / Ola**: fare-estimate APIs exist but are partner/enterprise-gated.
- **Rapido**: no consumer API of any kind, only driver-side.

So the estimate is, and has to stay, your own formula:
`fare = base + per_km × distance + per_min × duration` (× surge if you have
a signal for it — none of these apps expose surge publicly, so it defaults
to 1.0).

The formula itself was already right in your original code — what makes it
*good* is not the formula, it's calibrating `base/per_km/per_min` against
real observed fares instead of guessed numbers. `rides.py` has the step-by-step
in its module docstring: sample ~15-20 real routes by hand across
apps/vehicle types once, fit the three constants per (provider, vehicle
type) with linear regression, redo every few months. That's the only
approach here that's both accurate-ish and doesn't involve scraping
session-gated fare screens.

## Deep links — verified, not guessed
- **Uber**: officially documented (`developer.uber.com/docs/deep-linking`).
  `pickup[lat/lon]` + `dropoff[lat/lon]` prefill works with no API key.
- **Ola**: officially documented (`developers.olacabs.com/docs/deep-linking`).
  `lat/lng` + `drop_lat/drop_lng` + `category` prefill works standalone;
  full affiliate attribution needs a `utm_source` token from Ola's partner
  program, but that's not required for the link to open and prefill.
- **Rapido**: **no public documented scheme.** I didn't invent one — that
  would silently break or misfire. It falls back to opening
  `rapido.bike` with a `deep_link_note` flagging that the user has to
  re-enter pickup/drop. If you want real prefill here, the only path is
  manually reverse-engineering the app's actual intent/URL scheme off a
  real device (e.g. `adb logcat` during a real booking) — flag that to
  yourself as unsupported/reverse-engineered, not a stable integration.

## `/rides` request/response shape now
```json
POST /rides
{"profile_id": "user_5star",
 "pickup_text": "Kempegowda Airport, Bangalore",
 "drop_text": "Whitefield, Bangalore"}
```
Returns `distance_km`, `duration_min` (from GraphHopper) and a `platforms`
list — one entry per app, each holding 3 vehicle-type options with fare,
ETA, `is_preferred`, `deep_link`, and reason text. That maps directly onto
"comparison screen shows 3 apps, each showing 3 options, preferred one
highlighted."

## Still open / needs your input before further coding
- `GRAPHHOPPER_API_KEY` needs to be set (free tier signup at
  graphhopper.com) — not hardcoded anywhere, on purpose.
- No live rate calibration has been done yet — `RATE_CARD` in `rides.py`
  is still ballpark numbers, same caveat as the old `VEHICLE_RATES`.
- Surge is not modeled (defaults to 1.0) since none of these three apps
  expose it publicly — flag if you want a manual peak-hour multiplier
  (e.g. time-of-day heuristic) instead.
