"""
algorithms.py  —  The 7 core algorithms of the AI Trip Planner.
All computation is pure Python/math. No LLM involved here.
Called by workflow.py AFTER the LLM agents gather raw data,
BEFORE the itinerary agent writes the narrative.
"""

import math
import random
from datetime import datetime, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# ALGORITHM 1 — Haversine Distance
# ─────────────────────────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Return great-circle distance in km between two GPS coordinates.
    Accounts for Earth's curvature. O(1) per pair.
    """
    R = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi    = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(min(a, 1.0)))


def _parse_coord(place: dict, key_lat="lat", key_lon="lon"):
    """Safely extract float lat/lon from a place dict."""
    try:
        lat = float(place.get(key_lat) or place.get("latitude") or 0)
        lon = float(place.get(key_lon) or place.get("longitude") or 0)
        return lat, lon
    except (TypeError, ValueError):
        return 0.0, 0.0


# ─────────────────────────────────────────────────────────────────────────────
# ALGORITHM 2 — Travel-Time Estimator
# ─────────────────────────────────────────────────────────────────────────────

def travel_time(km: float) -> tuple:
    """
    Return (minutes: int, mode: str) based on distance.
    Walk <1 km | Auto-rickshaw 1-5 km | Taxi >5 km
    """
    if km < 1.0:
        return (max(5, round(km / 5.0 * 60)), "walking")
    elif km < 5.0:
        return (max(5, round(km / 20.0 * 60)), "auto-rickshaw")
    else:
        return (max(10, round(km / 35.0 * 60)), "taxi")


# ─────────────────────────────────────────────────────────────────────────────
# ALGORITHM 3 — Preference Scoring
# ─────────────────────────────────────────────────────────────────────────────

def preference_score(place: dict, interests: list,
                     daily_activity_budget: float) -> float:
    """
    Composite score in [0, 1] balancing interest match, rating, and budget fit.
    Weights: tag overlap 50% | rating 30% | budget fit 20%
    """
    tags     = [t.lower() for t in place.get("tags", [])]
    rating   = float(place.get("rating", 3.5))
    fee      = float(place.get("entry_fee_inr", 0) or 0)

    # Tag overlap — fraction of interests matched
    if interests:
        matched  = sum(1 for i in interests if i.lower() in tags or
                       any(i.lower() in t for t in tags))
        overlap  = matched / len(interests)
    else:
        overlap  = 0.5  # neutral if no interests stated

    # Rating normalised to [0, 1]
    norm_rating = (rating - 1.0) / 4.0

    # Budget fit — 1.0 if free, approaches 0 as fee reaches daily budget
    budget_fit = 1.0 - min(fee / max(daily_activity_budget, 1.0), 1.0)

    return round(0.50 * overlap + 0.30 * norm_rating + 0.20 * budget_fit, 4)


def score_and_rank_places(places: list, interests: list,
                          daily_activity_budget: float) -> list:
    """
    Score every place and return sorted list (highest score first).
    Adds 'algo_score' field to each place dict.
    """
    for place in places:
        place["algo_score"] = preference_score(
            place, interests, daily_activity_budget)
    ranked = sorted(places, key=lambda p: p["algo_score"], reverse=True)
    print("Preference Scoring: ranked " + str(len(ranked)) + " places")
    if ranked:
        top = ranked[0]
        print("  Top: " + top.get("name", "?") + " (score=" + str(top["algo_score"]) + ")")
    return ranked


# ─────────────────────────────────────────────────────────────────────────────
# ALGORITHM 4 — K-Means Geo-Clustering
# ─────────────────────────────────────────────────────────────────────────────

def _centroid(cluster_places: list) -> tuple:
    """Return (avg_lat, avg_lon) for a list of places."""
    if not cluster_places:
        return (0.0, 0.0)
    lats = [_parse_coord(p)[0] for p in cluster_places]
    lons = [_parse_coord(p)[1] for p in cluster_places]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def kmeans_cluster(places: list, k: int,
                   max_iterations: int = 12) -> list:
    """
    Assign each place to a day-group (0..k-1) using K-Means++ seeding
    and Lloyd's algorithm. Adds 'day_group' field to each place dict.
    Returns places list with day_group assigned.
    """
    if not places or k <= 0:
        return places

    k = min(k, len(places))
    coords = [_parse_coord(p) for p in places]

    # K-Means++ initialisation
    seed_idx  = random.randrange(len(coords))
    centroids = [coords[seed_idx]]

    while len(centroids) < k:
        distances = []
        for c in coords:
            d = min(haversine(c[0], c[1], cx[0], cx[1]) for cx in centroids)
            distances.append(d)
        total = sum(distances) or 1.0
        probs = [d / total for d in distances]
        r = random.random()
        cumul = 0.0
        chosen = len(coords) - 1
        for idx, p in enumerate(probs):
            cumul += p
            if cumul >= r:
                chosen = idx
                break
        centroids.append(coords[chosen])

    # Lloyd's iterations
    assignments = [0] * len(coords)
    for iteration in range(max_iterations):
        new_assignments = []
        for c in coords:
            dists = [haversine(c[0], c[1], cx[0], cx[1]) for cx in centroids]
            new_assignments.append(dists.index(min(dists)))

        if new_assignments == assignments:
            print("K-Means: converged at iteration " + str(iteration + 1))
            break
        assignments = new_assignments

        # Recompute centroids
        new_centroids = []
        for j in range(k):
            cluster = [coords[i] for i, a in enumerate(assignments) if a == j]
            new_centroids.append(_centroid(
                [{"lat": c[0], "lon": c[1]} for c in cluster]
            ) if cluster else centroids[j])
        centroids = new_centroids

    for i, place in enumerate(places):
        place["day_group"] = assignments[i]

    # Log cluster sizes
    for j in range(k):
        members = [p.get("name", "?") for p in places if p.get("day_group") == j]
        print("  Cluster Day " + str(j + 1) + ": " + ", ".join(members))

    return places


# ─────────────────────────────────────────────────────────────────────────────
# ALGORITHM 5 — Nearest-Neighbour TSP
# ─────────────────────────────────────────────────────────────────────────────

def nearest_neighbour_tsp(places: list,
                          hotel_lat: float,
                          hotel_lon: float) -> list:
    """
    Order places in a single day cluster using greedy nearest-neighbour TSP.
    Starts from hotel coordinates. Returns ordered list.
    O(n²) where n = places in the day cluster.
    """
    if not places:
        return []

    unvisited = list(places)
    ordered   = []
    cur_lat, cur_lon = hotel_lat, hotel_lon

    while unvisited:
        nearest = min(
            unvisited,
            key=lambda p: haversine(cur_lat, cur_lon,
                                    _parse_coord(p)[0],
                                    _parse_coord(p)[1])
        )
        ordered.append(nearest)
        unvisited.remove(nearest)
        cur_lat, cur_lon = _parse_coord(nearest)

    # Log total route distance
    total_km = 0.0
    prev_lat, prev_lon = hotel_lat, hotel_lon
    for p in ordered:
        lat, lon = _parse_coord(p)
        total_km += haversine(prev_lat, prev_lon, lat, lon)
        prev_lat, prev_lon = lat, lon
    print("  TSP route: " + " → ".join(p.get("name", "?") for p in ordered))
    print("  Total route distance: " + str(round(total_km, 2)) + " km")

    return ordered


# ─────────────────────────────────────────────────────────────────────────────
# ALGORITHM 6 — Greedy Day Scheduler
# ─────────────────────────────────────────────────────────────────────────────

MEAL_SLOTS = [
    {"name": "Breakfast", "hour": 8,  "duration_min": 45,  "meal_type": "breakfast"},
    {"name": "Lunch",     "hour": 13, "duration_min": 60,  "meal_type": "lunch"},
    {"name": "Dinner",    "hour": 19, "duration_min": 75,  "meal_type": "dinner"},
]


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
    Build a single day's timed activity list.

    Weather rule (FIXED):
    - Bad weather (heat/rain) → try to skip outdoor places in 11:00-17:00 window
    - BUT if no other option exists for that slot, schedule the place anyway
      with a caution note — empty afternoon is worse than a cautioned visit.

    Other rules:
    - Travel time inserted between every stop
    - Opening hours enforced — skip if closed
    - Budget enforced — skip if over activities budget
    - Meals at 08:00 (breakfast), 13:00 (lunch), 19:00 (dinner)
    """
    clock      = datetime(2000, 1, 1, 8, 0)
    activities = []
    spent_act  = 0.0
    meals_done = set()
    prev_lat, prev_lon = hotel_lat, hotel_lon

    # ── Pre-scan: count how many places can fill 11:00-17:00 bad-weather slot ──
    # If zero indoor options exist, we must show outdoor places with caution
    indoor_options = [p for p in ordered_places if not p.get("is_outdoor", True)]
    has_indoor_afternoon = len(indoor_options) > 0

    def insert_meal(meal_slot, override_clock=None):
        """Insert a meal break. override_clock lets us insert at a fixed time."""
        if meal_slot["meal_type"] in meals_done:
            return
        t = override_clock if override_clock else clock
        rest = restaurants[0] if restaurants else None
        if len(restaurants) > 1 and meal_slot["meal_type"] == "lunch":
            rest = restaurants[1]
        elif len(restaurants) > 2 and meal_slot["meal_type"] == "dinner":
            rest = restaurants[-1]
        cost_pp = float(rest.get("avg_cost_per_person_inr", 300)) if rest else 300
        activities.append({
            "time":        t.strftime("%H:%M"),
            "activity":    meal_slot["name"],
            "description": (rest.get("name", "Local restaurant") + " — " +
                           rest.get("cuisine", "Local cuisine")) if rest else "Local meal",
            "location":    rest.get("location", "Nearby restaurant") if rest else "Nearby",
            "duration":    str(meal_slot["duration_min"]) + " min",
            "cost_inr":    round(cost_pp * travelers, 2),
            "is_meal":     True,
            "meal_type":   meal_slot["meal_type"],
            "travel_note": "",
            "caution":     "",
        })
        meals_done.add(meal_slot["meal_type"])

    # Insert breakfast at 08:00
    insert_meal(MEAL_SLOTS[0])
    clock += timedelta(minutes=MEAL_SLOTS[0]["duration_min"])

    for place in ordered_places:
        # ── Travel time ───────────────────────────────────────────────────
        lat, lon    = _parse_coord(place)
        km          = haversine(prev_lat, prev_lon, lat, lon)
        t_min, mode = travel_time(km)
        clock      += timedelta(minutes=t_min)
        travel_note = str(t_min) + " min by " + mode + " (" + str(round(km, 1)) + " km)"

        # ── Lunch insertion ───────────────────────────────────────────────
        if clock.hour >= 13 and "lunch" not in meals_done:
            insert_meal(MEAL_SLOTS[1])
            clock += timedelta(minutes=MEAL_SLOTS[1]["duration_min"])

        # ── Opening hours ─────────────────────────────────────────────────
        try:
            open_h, open_m   = map(int, place.get("open_time",  "09:00").split(":"))
            close_h, close_m = map(int, place.get("close_time", "18:00").split(":"))
        except (ValueError, AttributeError):
            open_h, open_m   = 9, 0
            close_h, close_m = 18, 0

        open_dt   = datetime(2000, 1, 1, open_h, open_m)
        close_dt  = datetime(2000, 1, 1, close_h, close_m)
        visit_hrs = float(place.get("visit_duration_hrs", 1.5))

        if clock < open_dt:
            clock = open_dt

        if clock + timedelta(hours=visit_hrs) > close_dt:
            print("  SKIP (closed): " + place.get("name", "?") +
                  " closes " + place.get("close_time", "18:00") +
                  ", arrive " + clock.strftime("%H:%M"))
            continue

        if clock.hour >= 21:
            print("  STOP: day cutoff at " + clock.strftime("%H:%M"))
            break

        # ── Weather check (FIXED) ─────────────────────────────────────────
        # Bad weather window: 11:00 – 17:00 on extreme heat or rainy days
        is_outdoor   = bool(place.get("is_outdoor", True))
        in_bad_window = not is_outdoor_ok and 11 <= clock.hour < 17
        caution_note  = ""

        if in_bad_window and is_outdoor:
            # Weather is a preference, not a hard exclusion. A strict skip here
            # can leave an entire day with meals only. Keep the attraction and
            # surface a clear caution so the traveller can decide.
            caution_note = (
                "⚠️ Outdoor visit during unfavourable weather. Check the latest "
                "forecast before leaving, carry water, and use sun/rain protection."
            )
            print("  CAUTION (weather): " + place.get("name", "?") +
                  " retained despite weather restriction")

        # ── Budget check ──────────────────────────────────────────────────
        entry_fee = float(place.get("entry_fee_inr", 0) or 0) * travelers
        if spent_act + entry_fee > act_budget and entry_fee > 0:
            print("  SKIP (budget): " + place.get("name", "?") +
                  " Rs " + str(int(entry_fee)) +
                  " | remaining Rs " + str(int(act_budget - spent_act)))
            continue

        # ── Schedule the place ────────────────────────────────────────────
        activities.append({
            "time":        clock.strftime("%H:%M"),
            "activity":    place.get("name", "Visit"),
            "description": place.get("description", ""),
            "location":    place.get("location", ""),
            "duration":    str(visit_hrs) + " hrs",
            "cost_inr":    round(entry_fee, 2),
            "is_meal":     False,
            "travel_note": travel_note,
            "caution":     caution_note,   # empty string if weather is fine
        })
        spent_act  += entry_fee
        prev_lat, prev_lon = lat, lon
        clock += timedelta(hours=visit_hrs)

    # ── Dinner ────────────────────────────────────────────────────────────────
    if "dinner" not in meals_done:
        if clock.hour < 19:
            clock = datetime(2000, 1, 1, 19, 0)
        insert_meal(MEAL_SLOTS[2])

    # ── Lunch fallback: insert at 13:00 if it was never triggered ─────────────
    if "lunch" not in meals_done:
        lunch_idx = next(
            (i for i, a in enumerate(activities) if a.get("meal_type") == "dinner"),
            len(activities)
        )
        rest = (restaurants[1] if len(restaurants) > 1
                else restaurants[0] if restaurants else None)
        cost_pp = float(rest.get("avg_cost_per_person_inr", 300)) if rest else 300
        activities.insert(lunch_idx, {
            "time":        "13:00",
            "activity":    "Lunch",
            "description": rest.get("name", "Local restaurant") + " — " +
                           rest.get("cuisine", "Local cuisine") if rest else "Local restaurant",
            "location":    rest.get("location", "Nearby") if rest else "Nearby",
            "duration":    "60 min",
            "cost_inr":    round(cost_pp * travelers, 2),
            "is_meal":     True,
            "meal_type":   "lunch",
            "travel_note": "",
            "caution":     "",
        })

    # ── Build meals summary ───────────────────────────────────────────────────
    meals = {}
    for a in activities:
        if a.get("is_meal"):
            mt = a.get("meal_type", "")
            if mt:
                meals[mt] = a["activity"] + " at " + a["description"]

    total_cost = sum(float(a.get("cost_inr", 0) or 0) for a in activities)

    return {
        "activities":         activities,
        "meals":              meals,
        "estimated_cost_inr": round(total_cost, 2),
        "weather_note":       weather_note,
        "date_label":         date_label,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ALGORITHM 7 — INR Budget Allocator  (already in budget_allocator.py)
# Exposed here as a wrapper for unified import in workflow
# ─────────────────────────────────────────────────────────────────────────────

def get_budget_envelopes(budget_inr: float, duration: int,
                         travelers: int, travel_type: str) -> dict:
    """Thin wrapper — delegates to budget_allocator.allocate()."""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from budget_allocator import allocate
    return allocate(budget_inr, duration, travelers, travel_type)


# ─────────────────────────────────────────────────────────────────────────────
# MASTER PIPELINE — run all 6 deterministic algorithms in sequence
# (Budget allocator already ran earlier in workflow; results passed in via env)
# ─────────────────────────────────────────────────────────────────────────────

def run_algorithm_pipeline(places: list,
                            restaurants: list,
                            travel_details: dict,
                            weather: dict,
                            env: dict) -> list:
    """
    Execute algorithms 1-6 on raw LLM-gathered data and return a
    structured list of day dicts ready for the ItineraryAgent's LLM
    to add titles, narratives, tips, and event notes.

    Steps:
        1. Preference Scoring  → ranked places
        2. K-Means Clustering  → day-group assignment
        3. Nearest-Neighbour TSP → ordered places per day
        4. Travel-Time (inside scheduler)
        5. Haversine (inside TSP + scheduler)
        6. Greedy Scheduler   → timed, feasible activity list per day
    """
    destination  = travel_details.get("destination", "Unknown")
    duration     = int(travel_details.get("duration", 5))
    interests    = travel_details.get("interests", [])
    travelers    = int(travel_details.get("travelers", 2))
    hotel_lat    = float(travel_details.get("hotel_lat", 0.0))
    hotel_lon    = float(travel_details.get("hotel_lon", 0.0))

    act_per_day  = env["activities_per_day"]
    act_total    = env["activities_total"]

    # Day weather lookup — map date string → day weather info
    daily_wx = {}
    for dw in weather.get("daily_forecast", []):
        daily_wx[dw.get("date", "")] = dw

    from datetime import date as _date, timedelta as _td
    raw_start = travel_details.get("start_date") or _date.today().isoformat()
    try:
        trip_start = _date.fromisoformat(raw_start)
    except ValueError:
        trip_start = _date.today()

    # ── Step 1: Preference Scoring ───────────────────────────────────────────
    print("\n[ALGO] Step 1 — Preference Scoring")
    ranked = score_and_rank_places(places, interests, act_per_day)

    # Take top (duration * 5) places to give each day ~5 options
    # This provides buffer: even if 2 are skipped (closed/budget/weather),
    # there are still 3 left to fill the morning, afternoon AND post-lunch slots
    top_places = ranked[:duration * 5]

    # ── Step 2: Balanced geo-aware distribution ─────────────────────────────
    # Pure K-Means can leave some day-groups empty or heavily unbalanced.
    # Distribute attractions in score order while preferring the closest
    # current day-centroid. The least-filled day is considered first, which
    # guarantees every day receives an attraction when enough places exist.
    print("\\n[ALGO] Step 2 — Balanced Geo-Clustering (" + str(duration) + " days)")
    day_buckets = [[] for _ in range(duration)]
    day_centroids = [None for _ in range(duration)]

    for place in top_places:
        lat, lon = _parse_coord(place)
        eligible = sorted(range(duration), key=lambda d: (len(day_buckets[d]), d))
        # Among equally small buckets, choose the geographically closest one.
        min_count = len(day_buckets[eligible[0]])
        eligible = [d for d in eligible if len(day_buckets[d]) == min_count]
        if eligible:
            chosen_day = min(
                eligible,
                key=lambda d: (
                    haversine(lat, lon, day_centroids[d][0], day_centroids[d][1])
                    if day_centroids[d] is not None else 0.0,
                    d
                )
            )
        else:
            chosen_day = 0

        day_buckets[chosen_day].append(place)
        place["day_group"] = chosen_day
        # Update centroid incrementally.
        prev = day_centroids[chosen_day]
        if prev is None:
            day_centroids[chosen_day] = (lat, lon)
        else:
            n = len(day_buckets[chosen_day])
            day_centroids[chosen_day] = (
                prev[0] + (lat - prev[0]) / n,
                prev[1] + (lon - prev[1]) / n,
            )

    # ── Steps 3–6: Per-day TSP + Greedy Scheduler ────────────────────────────
    algo_days = []
    for day_idx in range(duration):
        day_num     = day_idx + 1
        day_date    = trip_start + _td(days=day_idx)
        date_str    = day_date.isoformat()
        date_label  = day_date.strftime("%B %d, %Y (%A)")

        # Each day gets its own balanced bucket; no overlapping fallback slices.
        day_places = list(day_buckets[day_idx])
        if not day_places and ranked:
            # If there are fewer unique attractions than trip days, repeat the
            # best-ranked attraction rather than returning a meals-only day.
            fallback = dict(ranked[day_idx % len(ranked)])
            fallback["is_repeat_suggestion"] = True
            day_places = [fallback]

        # Weather for this day
        dw = daily_wx.get(date_str, {})
        is_outdoor_ok = dw.get("is_outdoor_ok", True)
        weather_note  = dw.get("advice", "")
        if not weather_note:
            weather_note = weather.get("advice", "")

        print("\n[ALGO] Day " + str(day_num) + " — " + date_label)
        print("  Places in cluster: " + str(len(day_places)))
        print("  Weather: " + dw.get("condition", "Unknown") +
              " | Outdoor OK: " + str(is_outdoor_ok))

        # ── Step 3: Nearest-Neighbour TSP ────────────────────────────────
        print("[ALGO] Step 3 — Nearest-Neighbour TSP (Day " + str(day_num) + ")")
        ordered = nearest_neighbour_tsp(day_places, hotel_lat, hotel_lon)

        # ── Steps 4 & 5 embedded in scheduler ────────────────────────────
        print("[ALGO] Steps 4+5+6 — Travel-Time + Haversine + Greedy Scheduler")
        day_result = schedule_day(
            ordered_places   = ordered,
            restaurants      = restaurants,
            hotel_lat        = hotel_lat,
            hotel_lon        = hotel_lon,
            act_budget       = act_per_day,
            travelers        = travelers,
            date_label       = date_label,
            weather_note     = weather_note,
            is_outdoor_ok    = is_outdoor_ok,
        )

        day_result["day"]         = day_num
        day_result["actual_date"] = date_str
        algo_days.append(day_result)

        print("  Scheduled " + str(len(day_result["activities"])) + " slots" +
              " | Estimated cost: Rs " + str(int(day_result["estimated_cost_inr"])))

    print("\n[ALGO] Pipeline complete — " + str(len(algo_days)) + " days scheduled")
    return algo_days
