"""
Deep link builders for the handoff step (comparison screen -> real app).

Status per provider, as of this writing:

- Uber: OFFICIALLY DOCUMENTED (https://developer.uber.com/docs/deep-linking).
  Universal link works with just lat/lon, no API key/partnership needed.

- Ola: OFFICIALLY DOCUMENTED (https://developers.olacabs.com/docs/deep-linking).
  Works with just lat/lon/category for basic prefill. Full fidelity
  (affiliate attribution, guaranteed category selection) needs an
  affiliate `utm_source` token from Ola's partner program - link still
  opens and prefills pickup/drop without one, just without attribution.

- Rapido: NOT DOCUMENTED. Rapido has no public deep-linking spec for
  prefilling pickup/drop coordinates (unlike Uber/Ola). All that's public
  is the generic `rapido://` app-open scheme and the rapido.bike web page.
  Don't guess at undocumented query params - they can silently break or,
  worse, get treated as a malformed request by the app. Safer options:
    1) Open https://rapido.bike (their web entry point) and let the user
       search again - it's zero-prefill but always works.
    2) If you have access to a couple of test devices, inspect the app's
       actual outbound intents (Android: adb logcat around a real booking
       flow) to reverse-engineer the real scheme - but treat that as
       unstable/reverse-engineered, not a supported integration.
  This module ships option (1) and flags it with `deep_link_note`.
"""

from typing import Optional, Tuple

VEHICLE_TO_UBER_PRODUCT_HINT = {
    # Uber's product_id is city- and catalog-specific (comes from their
    # Products endpoint, which is partner-gated). Without it, omit
    # product_id entirely and let the user pick the ride type inside the
    # app - the pickup/dropoff prefill still saves them the typing.
}


def uber_link(
    pickup: Tuple[float, float],
    drop: Tuple[float, float],
    pickup_label: Optional[str] = None,
    drop_label: Optional[str] = None,
) -> str:
    plat, plon = pickup
    dlat, dlon = drop
    parts = [
        "https://m.uber.com/ul/?action=setPickup",
        f"pickup[latitude]={plat}",
        f"pickup[longitude]={plon}",
        f"dropoff[latitude]={dlat}",
        f"dropoff[longitude]={dlon}",
    ]
    if pickup_label:
        parts.append(f"pickup[nickname]={pickup_label}")
    if drop_label:
        parts.append(f"dropoff[nickname]={drop_label}")
    return "&".join(parts)


# Ola's `category` values recognized by the deep link (from their docs).
_OLA_CATEGORY = {
    "Bike": "bike",
    "Auto": "auto",
    "Cab": "mini",  # closest generic economy-cab category
}


def ola_link(
    pickup: Tuple[float, float],
    drop: Tuple[float, float],
    vehicle_type: str,
    drop_label: Optional[str] = None,
) -> str:
    plat, plon = pickup
    dlat, dlon = drop
    category = _OLA_CATEGORY.get(vehicle_type, "mini")
    parts = [
        "https://book.olacabs.com/?",
        f"lat={plat}&lng={plon}",
        f"drop_lat={dlat}&drop_lng={dlon}",
        f"category={category}",
    ]
    if drop_label:
        parts.append(f"drop_address={drop_label}")
    return "&".join(parts).replace("?&", "?")


def rapido_link(*_args, **_kwargs) -> Tuple[str, str]:
    """
    Returns (url, note). No documented prefill exists, so this always opens
    the generic web entry point and the caller should surface the note.
    """
    return (
        "https://rapido.bike",
        "Rapido has no documented deep-link prefill - this opens their "
        "site/app and the user re-enters pickup/drop.",
    )
