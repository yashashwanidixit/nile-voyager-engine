from .models import UserProfile

PROFILES = {
    "user_5star": UserProfile(
        id="user_5star",
        name="Ananya (Luxury preference)",
        rating_min=4.5,
        rating_max=5.0,
        rating_label="5-star / luxury",
        preferred_vehicle_type="Cab",
    ),
    "user_4star": UserProfile(
        id="user_4star",
        name="Rahul (Comfort/Budget preference)",
        rating_min=3.8,
        rating_max=4.49,
        rating_label="4-star / comfort",
        preferred_vehicle_type="Auto",
    ),
}


def get_profile(profile_id: str) -> UserProfile:
    if profile_id not in PROFILES:
        raise ValueError(f"Unknown profile_id '{profile_id}'. Valid: {list(PROFILES)}")
    return PROFILES[profile_id]
