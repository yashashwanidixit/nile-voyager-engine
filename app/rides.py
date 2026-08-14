"""
Fare estimator for the comparison screen.

Why this replaced the old single-provider (Rapido-only) module:
the new pipeline shows one card per ride app (Uber / Ola / Rapido), and
within each card, three vehicle-type options (Bike / Auto / Cab) with the
user's preferred type highlighted. Availability isn't checked (can't be,
without partner access) - all three options are always shown per app.

On price accuracy - there is no live-price API available to a normal dev for
any of these three apps (Uber and Ola gate fare-estimate APIs behind partner
agreements; Rapido has no consumer API at all). The formula below is the
correct approach; the number quality only improves if you keep RATE_CARD
below calibrated against reality:

  HOW TO CALIBRATE (do this instead of scraping session-gated fare screens):
    1. Pick ~15-20 varied routes around Bangalore (short/medium/long,
       peak/off-peak).
    2. For each route, manually open Uber/Ola/Rapido and note the quoted
       fare per vehicle type (a spreadsheet, done once, takes an afternoon).
    3. Fit `fare = base + per_km*distance_km + per_min*duration_min` per
       (provider, vehicle_type) via simple linear regression (numpy.polyfit
       or sklearn) on that sample.
    4. Drop the fitted base/per_km/per_min into RATE_CARD below.
    5. Redo this every few months - fares drift, and surge patterns shift.
  This gets you estimates that track reality far better than guessed
  constants, without touching any login-gated scraping.
"""

from dataclasses import dataclass
from typing import Dict, Tuple

from app.deeplinks import ola_link, rapido_link, uber_link
from app.models import PlatformRides, RideOption, UserProfile

VEHICLE_TYPES = ("Bike", "Auto", "Cab")
PROVIDERS = ("Uber", "Ola", "Rapido")


@dataclass
class RateCard:
    base: float       # flat pickup fee (INR)
    per_km: float     # INR per km
    per_min: float     # INR per minute (covers time stuck in traffic, not just distance)


# Starting values only - see calibration note above. These are rough,
# publicly-known Bangalore ballpark rates as of the model's training data,
# NOT scraped or live figures, and should be replaced with your own
# calibrated numbers before you rely on the output.
RATE_CARD: Dict[str, Dict[str, RateCard]] = {
    "Uber": {
        "Bike": RateCard(base=20, per_km=6.5, per_min=1.0),
        "Auto": RateCard(base=30, per_km=11.5, per_min=1.5),
        "Cab":  RateCard(base=55, per_km=13.5, per_min=1.8),
    },
    "Ola": {
        "Bike": RateCard(base=18, per_km=6.0, per_min=1.0),
        "Auto": RateCard(base=28, per_km=11.0, per_min=1.5),
        "Cab":  RateCard(base=50, per_km=13.0, per_min=1.7),
    },
    "Rapido": {
        "Bike": RateCard(base=15, per_km=6.0, per_min=0.8),
        "Auto": RateCard(base=25, per_km=11.0, per_min=1.3),
        "Cab":  RateCard(base=48, per_km=12.5, per_min=1.6),
    },
}

# Vehicles filter through traffic differently than a car does - GraphHopper's
# duration is car-based, so nudge ETA per vehicle type rather than reusing
# the raw car duration for a bike.
ETA_DURATION_MULTIPLIER = {
    "Bike": 0.75,   # two-wheelers cut through jams faster
    "Auto": 0.90,
    "Cab": 1.00,    # car baseline from GraphHopper
}


def _fare(rate: RateCard, distance_km: float, duration_min: float, surge_multiplier: float) -> float:
    raw = rate.base + rate.per_km * distance_km + rate.per_min * duration_min
    return round(raw * surge_multiplier, 0)


def _reason_for(vehicle_type: str, provider: str, profile: UserProfile, is_preferred: bool) -> str:
    if is_preferred:
        return (
            f"{provider} {vehicle_type} - matches your preferred ride type "
            f"({profile.preferred_vehicle_type})."
        )
    return f"{provider} {vehicle_type} - alternative to your usual {profile.preferred_vehicle_type}."


def estimate_all_platforms(
    profile: UserProfile,
    pickup: Tuple[float, float],
    drop: Tuple[float, float],
    distance_km: float,
    duration_min: float,
    pickup_label: str | None = None,
    drop_label: str | None = None,
    surge_multiplier: float = 1.0,
) -> list[PlatformRides]:
    """
    Builds the comparison-screen payload: one PlatformRides per app, each
    holding 3 RideOptions (Bike/Auto/Cab), with the profile's preferred
    vehicle_type flagged via is_preferred so the UI can highlight it.

    distance_km / duration_min: road distance + duration from
    app.routing.get_route() (GraphHopper), NOT straight-line haversine.
    surge_multiplier: pass >1.0 if you have any signal of peak-hour demand;
    defaults to 1.0 (no surge assumption) since none of these apps expose a
    real-time surge factor publicly.
    """
    platforms: list[PlatformRides] = []

    for provider in PROVIDERS:
        options = []
        for i, vehicle_type in enumerate(VEHICLE_TYPES):
            rate = RATE_CARD[provider][vehicle_type]
            adj_duration = duration_min * ETA_DURATION_MULTIPLIER[vehicle_type]
            fare = _fare(rate, distance_km, adj_duration, surge_multiplier)
            is_preferred = vehicle_type.lower() == profile.preferred_vehicle_type.lower()

            if provider == "Uber":
                link = uber_link(pickup, drop, pickup_label, drop_label)
                note = None
            elif provider == "Ola":
                link = ola_link(pickup, drop, vehicle_type, drop_label)
                note = None
            else:  # Rapido
                link, note = rapido_link()

            options.append(
                RideOption(
                    id=f"{provider.lower()}-{vehicle_type.lower()}-{i}",
                    provider=provider,
                    vehicle_type=vehicle_type,
                    fare_estimate=fare,
                    eta_minutes=int(adj_duration),
                    is_preferred=is_preferred,
                    reason=_reason_for(vehicle_type, provider, profile, is_preferred),
                    deep_link=link,
                    deep_link_note=note,
                )
            )

        # Preferred vehicle type first within each app's card, then cheapest.
        options.sort(key=lambda o: (not o.is_preferred, o.fare_estimate))
        platforms.append(PlatformRides(provider=provider, options=options))

    return platforms