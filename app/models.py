from dataclasses import dataclass
from typing import List, Optional


@dataclass
class UserProfile:
    """Hardcoded user preference profile (stage-1)."""
    id: str
    name: str
    rating_min: float           # inclusive lower bound of star rating this user wants (hotels)
    rating_max: float           # inclusive upper bound (hotels)
    rating_label: str           # human readable, used in the hotel "reason" text
    preferred_vehicle_type: str  # "Bike" | "Auto" | "Cab" -> highlighted in every platform's results


@dataclass
class Hotel:
    id: str
    name: str
    source: str                  # "MakeMyTrip" | "Agoda" | "Booking.com"
    rating: float                 # normalized to a 5.0 scale
    price_per_night: float
    address: str
    url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km_from_target: Optional[float] = None
    reason: Optional[str] = None


@dataclass
class RideOption:
    """One vehicle-type option within a single platform's card."""
    id: str
    provider: str              # "Uber" | "Ola"/"rapido"
    vehicle_type: str          # "Bike" | "Auto" | "Cab"
    fare_estimate: float
    eta_minutes: int
    is_preferred: bool         # True if this matches the user's preferred_vehicle_type
    reason: str
    deep_link: str
    deep_link_note: Optional[str] = None  # caveat, e.g. "no documented prefill for this app"


@dataclass
class PlatformRides:
    """All three vehicle-type options for a single ride-hailing app."""
    provider: str
    options: List[RideOption]
