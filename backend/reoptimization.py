"""Small, deterministic helpers for day-level itinerary re-optimization."""


def _normalise_place_name(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def filter_places_used_on_other_days(places: list, used_places: list) -> list:
    """Remove attractions assigned to other days, retaining this day's candidates."""
    excluded = {_normalise_place_name(name) for name in (used_places or []) if _normalise_place_name(name)}
    return [
        place for place in (places or [])
        if _normalise_place_name(place.get("name", "")) not in excluded
    ]
