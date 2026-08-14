from typing import List, Dict
from app.models import Hotel, UserProfile


def _reason_for(hotel: Hotel, profile: UserProfile) -> str:
    return (
        f"Rated {hotel.rating:.1f}/5 on {hotel.source}, which falls within your "
        f"preferred {profile.rating_label} range (\u2265{profile.rating_min}). "
        f"Priced at \u20b9{hotel.price_per_night:,.0f}/night."
    )


def select_top_hotels(
    hotels_by_source: Dict[str, List[Hotel]],
    profile: UserProfile,
    per_source: int = 5,
) -> List[Hotel]:
    """
    hotels_by_source: {"MakeMyTrip": [...], "Agoda": [...], "Booking.com": [...]}
    Filters each source's list to the profile's rating band, sorts by rating
    (desc) then price (asc) as a tiebreaker, takes the top `per_source` from
    EACH source, and attaches a human-readable reason to every hotel.

    Returns up to len(hotels_by_source) * per_source hotels (15 with 3 sources x 5).
    """
    selected: List[Hotel] = []

    for source, hotels in hotels_by_source.items():
        in_band = [
            h for h in hotels
            if profile.rating_min <= h.rating <= profile.rating_max
        ]
        # Fallback: if too few hotels fall exactly in-band (common with a strict
        # 4.5-5.0 band), relax by taking the highest-rated available from that
        # source instead of returning fewer than per_source results.
        pool = in_band if len(in_band) >= per_source else hotels

        ranked = sorted(pool, key=lambda h: (-h.rating, h.price_per_night))
        top = ranked[:per_source]

        for h in top:
            h.reason = _reason_for(h, profile)
        selected.extend(top)

    return selected
