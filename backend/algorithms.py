"""
Deterministic itinerary engine for AI Travel Planner.

Core guarantees:
- Every named attraction returned by discovery is surfaced exactly once:
  scheduled in a day or listed under additional_places.
- Budget and weather are advisory, never attraction-exclusion filters.
- Arrival at or after closing is not scheduled; arrival before closing may
  receive a shortened visit with a warning.
- Restaurants and hotels are recommendations only, never daily route stops.
- Meal slots are placeholders, not restaurant assignments.
- Geographic clustering precedes day scheduling; no assumed hotel (0,0) origin.
"""
import math
from datetime import date, timedelta


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres."""
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(min(1.0, a)))


def _parse_coord(place, key_lat="lat", key_lon="lon"):
    try:
        return (
            float(place.get(key_lat) or place.get("latitude") or 0),
            float(place.get(key_lon) or place.get("longitude") or 0),
        )
    except (TypeError, ValueError):
        return 0.0, 0.0


def travel_time(km):
    """Conservative approximate travel duration: (minutes, mode)."""
    if km < 1:
        return max(5, round(km / 4 * 60)), "walking"
    if km < 5:
        return max(8, round(km / 18 * 60)), "auto-rickshaw"
    return max(12, round(km / 30 * 60)), "taxi"


def preference_score(place, interests, daily_activity_budget=0):
    """Rank by interest match and rating only; cost is not a filter."""
    tags = [str(t).lower() for t in (place.get("tags") or [])]
    category = str(place.get("category", "")).lower()
    wanted = [str(i).lower() for i in (interests or [])]
    if wanted:
        overlap = sum(
            1 for item in wanted
            if item in category or any(item in tag for tag in tags)
        ) / len(wanted)
    else:
        overlap = 0.5
    try:
        rating = float(place.get("rating", 3.5))
    except (TypeError, ValueError):
        rating = 3.5
    rating_score = max(0.0, min(1.0, (rating - 1.0) / 4.0))
    return round(0.65 * overlap + 0.35 * rating_score, 4)


def score_and_rank_places(places, interests, daily_activity_budget=0):
    ranked = []
    for original in places or []:
        if not isinstance(original, dict) or not str(original.get("name", "")).strip():
            continue
        place = dict(original)
        place["algo_score"] = preference_score(place, interests, daily_activity_budget)
        ranked.append(place)
    ranked.sort(key=lambda p: p["algo_score"], reverse=True)
    print(f"Preference Scoring: ranked {len(ranked)} places")
    if ranked:
        print(f"  Top: {ranked[0].get('name', '?')} (score={ranked[0]['algo_score']})")
    return ranked


def _valid_coords(place):
    # Coordinates are usable only when resolved and verified by the geocoder.
    if place.get("coordinates_verified") is not True:
        return None
    lat, lon = _parse_coord(place)
    if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat != 0.0 or lon != 0.0):
        return lat, lon
    return None


def nearest_neighbour_tsp(places, hotel_lat=None, hotel_lon=None):
    """Order stops locally without treating missing hotel coordinates as (0,0)."""
    places = list(places or [])
    geo = [p for p in places if _valid_coords(p)]
    no_geo = [p for p in places if not _valid_coords(p)]
    if len(geo) < 2:
        return geo + no_geo
    coords = [_valid_coords(p) for p in geo]
    med_lat = sorted(c[0] for c in coords)[len(coords) // 2]
    med_lon = sorted(c[1] for c in coords)[len(coords) // 2]
    current = min(geo, key=lambda p: haversine(med_lat, med_lon, *_valid_coords(p)))
    ordered = [current]
    remaining = [p for p in geo if p is not current]
    while remaining:
        prev = _valid_coords(current)
        nxt = min(remaining, key=lambda p: haversine(*prev, *_valid_coords(p)))
        ordered.append(nxt)
        remaining.remove(nxt)
        current = nxt
    return ordered + no_geo


def kmeans_cluster(places, k, max_iterations=20):
    """Backward-compatible deterministic geographic day-group assignment."""
    groups = _balanced_geo_groups(places, max(1, int(k)))
    for group_idx, group in enumerate(groups):
        for place in group:
            place["day_group"] = group_idx
    return places


def get_budget_envelopes(budget_inr, duration, travelers, travel_type="default"):
    from budget_allocator import allocate
    return allocate(budget_inr, duration, travelers, travel_type)


def _valid_coords(place):
    # Coordinates are usable only when resolved and verified by the geocoder.
    if place.get("coordinates_verified") is not True:
        return None
    lat, lon = _parse_coord(place)
    if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat != 0.0 or lon != 0.0):
        return lat, lon
    return None


def _nearest_path(places):
    """Build a deterministic nearest-neighbour path without a fake (0,0) origin."""
    indexed = [(i, _valid_coords(p)) for i, p in enumerate(places)]
    remaining = {i for i, c in indexed if c is not None}
    path = []
    if remaining:
        coords = [_valid_coords(places[i]) for i in remaining]
        center_lat = sorted(c[0] for c in coords)[len(coords)//2]
        center_lon = sorted(c[1] for c in coords)[len(coords)//2]
        current = min(remaining, key=lambda i: haversine(
            center_lat, center_lon, *_valid_coords(places[i])))
        path.append(current)
        remaining.remove(current)
        while remaining:
            prev = _valid_coords(places[current])
            nxt = min(remaining, key=lambda i: haversine(
                *prev, *_valid_coords(places[i])))
            path.append(nxt)
            remaining.remove(nxt)
    # Places without valid coordinates are retained, never dropped.
    path.extend(i for i, c in indexed if c is None)
    return path


def _locality_key(place):
    """Return a usable locality label without treating a state/country as a city."""
    raw = str(place.get("location") or "").strip()
    if not raw:
        return ""
    first = raw.split(",", 1)[0].strip().lower()
    generic = {"india", "rajasthan", "gujarat", "delhi", "madhya pradesh",
               "uttar pradesh", "maharashtra", "goa", "kerala", "unknown"}
    return "" if first in generic else " ".join(first.split())


def _balanced_geo_groups(places, duration, return_unselected=False):
    """Create compact locality clusters and select at most one cluster per day.

    Attractions within 35 km can share a sightseeing area. A matching locality
    label can join an unverified attraction to a verified neighbour, but two
    verified points more than 35 km apart are never joined merely because their
    text labels match. When there are more areas than trip days, lower-ranked
    areas remain visible as additional suggestions rather than being forced
    into an unrealistic day.
    """
    duration = max(1, int(duration))
    if not places:
        return [[] for _ in range(duration)]

    geo_indices = [i for i, place in enumerate(places) if _valid_coords(place)]
    no_geo_indices = [i for i, place in enumerate(places) if not _valid_coords(place)]
    parent = {i: i for i in geo_indices}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Only verified points form geographic clusters. An unverified point must
    # never bridge two distant verified cities through a shared text label.
    for pos, i in enumerate(geo_indices):
        for j in geo_indices[pos + 1:]:
            if haversine(*_valid_coords(places[i]), *_valid_coords(places[j])) <= 35.0:
                union(i, j)

    grouped = {}
    for i in geo_indices:
        grouped.setdefault(find(i), []).append(places[i])
    clusters = list(grouped.values())

    # Attach an unverified attraction to a single unambiguous nearby locality
    # cluster when possible. Otherwise keep it in a separate locality group.
    unmatched = {}
    for i in no_geo_indices:
        place = places[i]
        locality = _locality_key(place)
        matches = []
        if locality:
            for cluster_idx, cluster in enumerate(clusters):
                if any(_locality_key(member) == locality for member in cluster):
                    matches.append(cluster_idx)
        if len(matches) == 1:
            clusters[matches[0]].append(place)
        else:
            key = locality or f"__unknown_{i}"
            unmatched.setdefault(key, []).append(place)
    clusters.extend(unmatched.values())

    def cluster_rank(cluster):
        verified_count = sum(1 for p in cluster if _valid_coords(p))
        total_score = sum(float(p.get("algo_score", 0) or 0) for p in cluster)
        centroid_coords = [_valid_coords(p) for p in cluster if _valid_coords(p)]
        if centroid_coords:
            centroid = (sum(c[0] for c in centroid_coords) / len(centroid_coords),
                        sum(c[1] for c in centroid_coords) / len(centroid_coords))
        else:
            centroid = None
        return (verified_count, len(cluster), total_score, centroid)

    # Prefer areas with several reliably located attractions. Do not spread
    # distant towns across days just to fill every day with activities.
    clusters.sort(key=lambda c: cluster_rank(c)[:3], reverse=True)
    selected = clusters[:duration]
    unselected = clusters[duration:]

    # Order chosen sightseeing areas geographically to reduce transfers
    # between consecutive days. These transfers are NOT represented as
    # intra-day route legs; each day's inter-city transfer must be arranged
    # separately and is explicitly mentioned in the day's tip.
    with_centres = []
    for cluster in selected:
        cluster_coords = [_valid_coords(p) for p in cluster if _valid_coords(p)]
        centre = None
        if cluster_coords:
            centre = (sum(c[0] for c in cluster_coords) / len(cluster_coords),
                      sum(c[1] for c in cluster_coords) / len(cluster_coords))
        with_centres.append((cluster, centre))

    located = [(i, centre) for i, (_, centre) in enumerate(with_centres) if centre]
    ordered_indices = []
    if located:
        all_coords = [c for _, c in located]
        med = (sorted(c[0] for c in all_coords)[len(all_coords)//2],
               sorted(c[1] for c in all_coords)[len(all_coords)//2])
        current = min(located, key=lambda item: haversine(*med, *item[1]))[0]
        remaining = {i for i, _ in located}
        while remaining:
            if current not in remaining:
                current = min(remaining, key=lambda i: haversine(
                    *with_centres[current][1], *with_centres[i][1]))
            ordered_indices.append(current)
            remaining.remove(current)
            if remaining:
                current = min(remaining, key=lambda i: haversine(
                    *with_centres[ordered_indices[-1]][1], *with_centres[i][1]))
    ordered_indices.extend(i for i, (_, centre) in enumerate(with_centres)
                           if centre is None)

    days = [[] for _ in range(duration)]
    for day_idx, cluster_idx in enumerate(ordered_indices[:duration]):
        days[day_idx] = list(with_centres[cluster_idx][0])

    if return_unselected:
        return days, [place for cluster in unselected for place in cluster]
    return days


def _nearest_order_within_day(places):
    places = list(places)
    geo = [p for p in places if _valid_coords(p)]
    no_geo = [p for p in places if not _valid_coords(p)]
    if len(geo) < 2:
        return geo + no_geo
    # Start at the point closest to the geographic median, not hotel (0,0).
    coords = [_valid_coords(p) for p in geo]
    med_lat = sorted(c[0] for c in coords)[len(coords)//2]
    med_lon = sorted(c[1] for c in coords)[len(coords)//2]
    current = min(geo, key=lambda p: haversine(
        med_lat, med_lon, *_valid_coords(p)))
    ordered = [current]
    remaining = [p for p in geo if p is not current]
    while remaining:
        prev = _valid_coords(current)
        nxt = min(remaining, key=lambda p: haversine(*prev, *_valid_coords(p)))
        ordered.append(nxt)
        remaining.remove(nxt)
        current = nxt
    return ordered + no_geo


def _parse_hhmm(value, default):
    try:
        h, m = map(int, str(value or "").split(":")[:2])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h * 60 + m
    except (ValueError, TypeError):
        pass
    return default


def _fmt_minutes(value):
    value = max(0, min(int(value), 1439))
    return f"{value // 60:02d}:{value % 60:02d}"


def _day_weather_warning(place, daily_weather, weather):
    if not place.get("is_outdoor", True):
        return ""
    if not weather or not weather.get("data_available"):
        return ""
    outdoor_ok = daily_weather.get("is_outdoor_ok",
                                   weather.get("is_outdoor_ok", True))
    if outdoor_ok is False:
        advice = daily_weather.get("advice") or weather.get("advice") or \
                 "Check the latest forecast before visiting."
        return "Weather advisory: outdoor conditions may be unsuitable. " + str(advice)
    return ""


def schedule_day(ordered_places: list,
                 restaurants: list,
                 hotel_lat: float,
                 hotel_lon: float,
                 act_budget: float,
                 travelers: int,
                 date_label: str,
                 weather_note: str,
                 is_outdoor_ok: bool) -> dict:
    """
    Compatibility wrapper for callers that schedule one day.
    Restaurant recommendations are deliberately NOT inserted into the route.
    """
    day = _build_one_day(
        ordered_places, 0, date_label, {}, 
        {"data_available": bool(weather_note), "is_outdoor_ok": is_outdoor_ok,
         "advice": weather_note},
        act_budget, travelers
    )
    return {
        "activities": day["activities"],
        "meals": day["meals"],
        "estimated_cost_inr": day["estimated_cost_inr"],
        "weather_note": weather_note,
        "date_label": date_label,
        "additional_places": day["additional_places"],
        "route_warnings": day["route_warnings"],
    }


def _build_one_day(day_places, day_index, date_label, daily_weather,
                   weather, act_budget, travelers):
    # Keep locality-identifiable places in the itinerary even when coordinates
    # are unavailable. They are scheduled as standalone visits, never with a
    # fabricated route distance or travel-time estimate.
    verified_places = [p for p in day_places if _valid_coords(p)]
    unverified_places = [p for p in day_places if not _valid_coords(p)]
    additional = []
    ordered = _nearest_order_within_day(verified_places) + unverified_places
    clock = 9 * 60
    day_end = 19 * 60
    previous = None
    activities = []
    route_warnings = []

    for place in ordered:
        warnings = []
        travel_note = ""
        prev_coord = _valid_coords(previous) if previous is not None else None
        coord = _valid_coords(place)
        if not coord:
            travel_note = "Standalone visit: exact coordinates are unverified; confirm the location and arrange transport independently. No route time or distance is estimated."
            warnings.append("Location not verified: confirm the attraction's exact location and opening hours before departure; transport time is not estimated.")
        if previous is not None:
            if prev_coord and coord:
                km = haversine(*prev_coord, *coord)
                if km > 50:
                    additional.append({
                        **{k: place.get(k) for k in (
                            "name", "description", "location", "open_time", "close_time",
                            "entry_fee_inr", "image_url", "maps_link", "category"
                        )},
                        "reason": f"Outside this day's local sightseeing area ({km:.0f} km from the previous stop); plan it with a separate inter-city transfer.",
                        "schedule_status": "requires_intercity_transfer",
                    })
                    continue
                travel_min, mode = travel_time(km)
                travel_note = f"Approx. {travel_min} min by {mode} ({km:.1f} km)"
            else:
                travel_note = "Standalone visit: location coordinates are unverified. Confirm the exact location and arrange transport independently; no route time is estimated."

        opening = _parse_hhmm(place.get("open_time"), 9 * 60)
        closing = _parse_hhmm(place.get("close_time"), 18 * 60)
        if closing <= opening:
            closing = 18 * 60
        arrival = max(clock + (travel_min if previous is not None and prev_coord and coord else 0), opening)

        # Strict entry-closing rule: an attraction is schedulable only when
        # estimated arrival is strictly before its published closing time.
        # Do not create a tentative scheduled visit after entry has closed;
        # retain it as an additional candidate so the final fallback or user
        # can consider another trip day instead.
        closed_on_arrival = arrival >= closing
        if closed_on_arrival:
            additional.append({
                **{k: place.get(k) for k in (
                    "name", "description", "location", "open_time", "close_time",
                    "entry_fee_inr", "image_url", "maps_link", "category"
                )},
                "reason": (
                    f"Not scheduled: estimated arrival {_fmt_minutes(arrival)} is at or after "
                    f"entry closing time {_fmt_minutes(closing)}. Try another day or verify "
                    "special/extended entry hours."
                ),
                "schedule_status": "closed_before_arrival",
            })
            # No visit occurred, so do not advance the clock or previous stop.
            continue

        # A shortened visit is allowed only when arrival is before closing.
        try:
            requested = max(15, round(float(place.get("visit_duration_hrs", 1.5) or 1.5) * 60))
        except (ValueError, TypeError):
            requested = 90
        available = min(closing - arrival, day_end - arrival)
        actual = min(requested, available)
        if actual <= 0:
            # Leave a visible, actionable suggestion; the cross-day assignment
            # pass can move it to a later date with a viable time window.
            additional.append({
                **{k: place.get(k) for k in ("name", "description", "location", "open_time", "close_time", "entry_fee_inr", "image_url", "maps_link", "category")},
                "reason": "No usable time remains today; consider moving this attraction to another trip day.",
                "schedule_status": "not_enough_daylight",
            })
            continue
        if actual < requested:
            warnings.append(
                f"Limited visiting time: arrives at {_fmt_minutes(arrival)}, closes at "
                f"{_fmt_minutes(closing)}. Normal visit takes about {requested} minutes; "
                f"only {actual} minutes are available. Check last-entry rules."
            )

        weather_warning = _day_weather_warning(place, daily_weather, weather)
        if weather_warning:
            warnings.append(weather_warning)

        try:
            fee = max(0.0, float(place.get("entry_fee_inr", 0) or 0)) * max(1, travelers)
        except (ValueError, TypeError):
            fee = 0.0
        if fee > 0:
            warnings.append(
                f"Budget advisory: estimated entry fees are ₹{fee:,.0f} for "
                f"{travelers} traveller(s). The budget is a guideline, not an exclusion."
            )

        activities.append({
            "time": _fmt_minutes(arrival),
            "activity": place.get("name", "Attraction"),
            "description": place.get("description", ""),
            "location": place.get("location", ""),
            "duration": f"{actual} min",
            "cost_inr": round(fee, 2),
            "is_meal": False,
            "travel_note": travel_note,
            "caution": " ".join(warnings),
            "place_id": str(place.get("_source_index", place.get("name", ""))),
        })
        clock = arrival + actual
        previous = place

    # Every day has meal placeholders only; no restaurant is selected or routed.
    meals = {
        "breakfast": "08:00 — Breakfast (choose from Restaurant Recommendations)",
        "lunch": "13:00 — Lunch (choose from Restaurant Recommendations)",
        "dinner": "19:00 — Dinner (choose from Restaurant Recommendations)",
    }
    total = sum(float(a.get("cost_inr", 0) or 0) for a in activities)
    return {
        "day": day_index + 1,
        "title": f"Day {day_index + 1} — {date_label}",
        "date_label": date_label,
        "activities": activities,
        "additional_places": additional,
        "meals": meals,
        "estimated_cost_inr": round(total, 2),
        "weather_note": daily_weather.get("advice", ""),
        "tips": (f"Keep sightseeing within {(_locality_key(day_places[0]).title() if day_places and _locality_key(day_places[0]) else 'this local area')}. Any transfer from another city is separate and is not included in these activity times. Check local traffic, attraction timings and last-entry rules before departure."),
        "has_event": False,
        "event_name": None,
        "route_warnings": route_warnings,
    }


def run_algorithm_pipeline(places: list,
                            restaurants: list,
                            travel_details: dict,
                            weather: dict,
                            env: dict) -> list:
    """
    New pipeline:
      1) Retain all valid named attractions.
      2) Rank by interest/rating only (never by budget).
      3) Geographic nearest-path clustering into balanced daily groups.
      4) Nearest-neighbour ordering within each day.
      5) Realistic travel estimates between attractions (no fake hotel origin).
      6) Opening-hours validation with shortened-visit warnings.
      7) Weather and budget warnings, never exclusions.
      8) Meal placeholders; restaurants remain a separate recommendation list.
      9) Guarantee every fetched attraction appears either in activities or
         that day's additional_places.
    """
    from datetime import date as _date, timedelta as _td
    duration = max(1, int(travel_details.get("duration", 1)))
    travelers = max(1, int(travel_details.get("travelers", 1)))
    interests = travel_details.get("interests", [])
    raw_start = travel_details.get("start_date") or _date.today().isoformat()
    try:
        trip_start = _date.fromisoformat(str(raw_start))
    except ValueError:
        trip_start = _date.today()

    # Copy inputs to avoid mutating agent state or cached data.
    candidates = []
    for i, original in enumerate(places or []):
        if isinstance(original, dict) and str(original.get("name", "")).strip():
            item = dict(original)
            item["_source_index"] = i
            candidates.append(item)

    ranked = score_and_rank_places(candidates, interests, env.get("activities_per_day", 0))
    groups, outside_area_places = _balanced_geo_groups(ranked, duration, return_unselected=True)
    daily_forecasts = {
        str(d.get("date", "")): d
        for d in (weather or {}).get("daily_forecast", [])
        if isinstance(d, dict)
    }

    algo_days = []
    for day_idx in range(duration):
        day_date = trip_start + _td(days=day_idx)
        date_label = day_date.strftime("%B %d, %Y (%A)")
        daily_weather = daily_forecasts.get(day_date.isoformat(), {})
        day_places = groups[day_idx] if day_idx < len(groups) else []
        result = _build_one_day(
            day_places, day_idx, date_label, daily_weather, weather or {},
            env.get("activities_per_day", 0), travelers
        )
        result["actual_date"] = day_date.isoformat()
        result["all_place_names"] = [p.get("name", "") for p in day_places]
        algo_days.append(result)

    # Final empty-day fallback: use the remaining additional attractions as
    # candidates, not just coordinate-verified places. This is applied only
    # to days that still have no scheduled activities, so populated days and
    # their geographic clusters remain unchanged.
    scheduled_names = {
        str(activity.get("activity", "")).strip().casefold()
        for day in algo_days for activity in day["activities"]
    }
    remaining_candidates = [
        p for p in ranked
        if str(p.get("name", "")).strip().casefold() not in scheduled_names
    ]

    def day_anchor(day_idx):
        coords = [_valid_coords(p) for p in (groups[day_idx] if day_idx < len(groups) else [])]
        coords = [c for c in coords if c]
        if coords:
            return (sum(c[0] for c in coords) / len(coords),
                    sum(c[1] for c in coords) / len(coords))
        populated = []
        for other_idx, other_day in enumerate(algo_days):
            if other_idx == day_idx or not other_day["activities"]:
                continue
            name_set = {a.get("activity") for a in other_day["activities"]}
            coords = [_valid_coords(p) for p in ranked if p.get("name") in name_set]
            coords = [c for c in coords if c]
            if coords:
                populated.append((other_idx, coords[0]))
        if populated:
            return min(populated, key=lambda item: abs(item[0] - day_idx))[1]
        return None

    def locality_matches(a, b):
        ka, kb = _locality_key(a), _locality_key(b)
        return bool(ka and kb and ka == kb)

    for day_idx, day in enumerate(algo_days):
        if day["activities"] or not remaining_candidates:
            continue
        anchor = day_anchor(day_idx)

        # Prefer the nearest verified candidate. If none has coordinates,
        # retain a deterministic locality-based candidate rather than leaving
        # the day empty solely because geocoding failed.
        verified_remaining = [p for p in remaining_candidates if _valid_coords(p)]
        if anchor and verified_remaining:
            first = min(verified_remaining,
                        key=lambda p: haversine(*anchor, *_valid_coords(p)))
        elif verified_remaining:
            first = verified_remaining[0]
        else:
            original_group = groups[day_idx] if day_idx < len(groups) else []
            original_localities = {_locality_key(p) for p in original_group if _locality_key(p)}
            first = next(
                (p for p in remaining_candidates if _locality_key(p) in original_localities),
                remaining_candidates[0]
            )

        first_coord = _valid_coords(first)
        first_locality = _locality_key(first)
        fallback_group = [first]
        for candidate in remaining_candidates:
            if candidate is first:
                continue
            candidate_coord = _valid_coords(candidate)
            if first_coord and candidate_coord:
                if haversine(*first_coord, *candidate_coord) <= 35.0:
                    fallback_group.append(candidate)
            elif first_locality and _locality_key(candidate) == first_locality:
                fallback_group.append(candidate)

        remaining_candidates = [
            p for p in remaining_candidates if p not in fallback_group
        ]
        date_label = day.get("date_label", "")
        daily_weather = daily_forecasts.get(day.get("actual_date", ""), {})
        fallback_day = _build_one_day(
            fallback_group, day_idx, date_label, daily_weather, weather or {},
            env.get("activities_per_day", 0), travelers
        )
        if fallback_day["activities"]:
            transfer_km = (
                haversine(*anchor, *first_coord)
                if anchor and first_coord else None
            )
            if transfer_km is not None and transfer_km > 35:
                fallback_day["route_warnings"].append(
                    f"Long-distance transfer required: the nearest available sightseeing area is approximately {transfer_km:.0f} km away. Arrange inter-city transport separately; this transfer is not included in activity times."
                )
            elif not first_coord:
                fallback_day["route_warnings"].append(
                    "This day includes standalone attractions with unverified coordinates. Confirm exact locations and arrange transport independently; no distance or travel time is estimated."
                )
            else:
                fallback_day["route_warnings"].append(
                    "This day uses remaining attractions as a final fallback. Confirm local transport and opening hours before departure."
                )
            fallback_day["tips"] = (
                "This day was populated using remaining attractions as a final fallback. "
                "Check the location, opening hours and any transfer requirements before departure."
            )
            fallback_day["actual_date"] = day.get("actual_date")
            fallback_day["all_place_names"] = [p.get("name", "") for p in fallback_group]
            algo_days[day_idx] = fallback_day
            scheduled_names.update(
                str(a.get("activity", "")).strip().casefold()
                for a in fallback_day["activities"]
            )

    # Attractions not scheduled after the empty-day fallback remain visible
    # as additional suggestions. They are never silently dropped.
    for place in outside_area_places:
        if str(place.get("name", "")).strip().casefold() in scheduled_names:
            continue
        target = min(
            range(duration),
            key=lambda i: len(algo_days[i]["activities"]) + len(algo_days[i]["additional_places"])
        )
        algo_days[target]["additional_places"].append({
            **{k: place.get(k) for k in ("name", "description", "location", "open_time", "close_time", "entry_fee_inr", "image_url", "maps_link", "category")},
            "reason": "This attraction is in a different sightseeing area and was not included in the selected daily routes. Plan a separate inter-city transfer if you want to visit it.",
            "schedule_status": "outside_daily_area",
        })

    # Defensive final pass: if any candidate somehow isn't surfaced,
    # append it to the least-loaded day's additional suggestions.
    surfaced = set()
    for day in algo_days:
        surfaced.update(a.get("activity") for a in day["activities"])
        surfaced.update(p.get("name") for p in day["additional_places"])
    for p in ranked:
        if p.get("name") not in surfaced:
            target = min(
                range(duration),
                key=lambda i: len(algo_days[i]["activities"]) + len(algo_days[i]["additional_places"])
            )
            algo_days[target]["additional_places"].append({
                **{k: p.get(k) for k in ("name", "description", "location", "open_time", "close_time", "entry_fee_inr", "image_url", "maps_link", "category")},
                "reason": "Retained as an additional suggestion; no feasible timed slot was found.",
                "schedule_status": "additional",
            })

    print(f"[ALGO] New itinerary engine: retained {len(ranked)} attractions across {duration} days.")
    for day in algo_days:
        print(f"[ALGO] Day {day['day']}: {len(day['activities'])} scheduled, {len(day['additional_places'])} additional.")
    return algo_days

