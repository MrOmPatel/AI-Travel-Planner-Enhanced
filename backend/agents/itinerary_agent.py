"""
itinerary_agent.py  —  LLM adds narrative on top of real algorithm output.
All timings, routing, costs already computed by algorithms.py before this runs.
"""
import json, os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from .base_agent import BaseAgent
from budget_allocator import allocate
from tavily import TavilyClient


class ItineraryAgent(BaseAgent):

    def __init__(self):
        super().__init__()
        tavily_key = os.getenv("TAVILY_API_KEY")
        self.tavily = TavilyClient(api_key=tavily_key) if tavily_key else None

    def _fetch_events(self, destination: str) -> str:
        if not self.tavily:
            return "No event data"
        try:
            resp = self.tavily.search(
                "upcoming events festivals things happening in " + destination + " this week this month",
                max_results=3)
            results = resp.get("results", [])
            if not results:
                return "No event data"
            return "\n".join("- " + r.get("title","") + ": " + r.get("content","")[:200]
                             for r in results[:3])
        except Exception as e:
            print("Event search error: " + str(e))
            return "No event data"

    def _weather_context(self, weather: dict) -> str:
        if not weather or not weather.get("data_available"):
            return "Weather data not available."
        lines = ["Current: " + str(weather.get("condition","")) + " " +
                 str(weather.get("current_temp_c","")) + "C. " + weather.get("advice","")]
        for d in weather.get("daily_forecast", []):
            lines.append(d["date"] + ": " + d["condition"] + " " +
                         str(d["temp_c"]) + "C — " + d["advice"])
        return "\n".join(lines)

    def create_itinerary(self, travel_details: dict, places: list,
                         restaurants: list, weather: dict = None,
                         algo_days: list = None) -> list:

        destination   = travel_details.get("destination", "Unknown")
        duration      = int(travel_details.get("duration", 5))
        interests     = travel_details.get("interests", [])
        budget_inr    = float(travel_details.get("budget_inr", 80000))
        travelers     = int(travel_details.get("travelers", 2))
        travel_type   = travel_details.get("travel_type", "default")
        interests_str = ", ".join(interests)

        raw_start = travel_details.get("start_date") or date.today().isoformat()
        try:
            trip_start = date.fromisoformat(raw_start)
        except ValueError:
            trip_start = date.today()

        day_dates = [(trip_start + timedelta(days=i)).strftime("%B %d, %Y (%A)")
                     for i in range(duration)]
        days_until = (trip_start - date.today()).days
        season     = travel_details.get("season", "")

        env             = allocate(budget_inr, duration, travelers, travel_type)
        daily_food      = env["food_per_day"]
        meal_pp         = env["meal_budget_per_person"]
        act_per_day     = env["activities_per_day"]
        daily_total_cap = round((env["food_total"] + env["activities_total"]) / duration, 2)

        weather_ctx = self._weather_context(weather)
        events_ctx  = self._fetch_events(destination)

        # ── PATH A: real algorithm output — LLM narrative only ────────────────
        if algo_days:
            print("ItineraryAgent: enriching " + str(len(algo_days)) +
                  " algorithm-computed days with LLM narrative")
            return self._enrich(algo_days, destination, events_ctx, weather_ctx,
                                interests_str, travelers, day_dates, trip_start,
                                daily_total_cap)

        # ── PATH B: fallback — full LLM generation ────────────────────────────
        print("ItineraryAgent: no algo_days — using full LLM generation (fallback)")
        return self._llm_generate(
            destination, duration, interests_str, travelers, raw_start,
            day_dates, days_until, season, weather_ctx, events_ctx,
            places, restaurants, daily_total_cap, daily_food, meal_pp,
            act_per_day, trip_start
        )

    # ── PATH A ────────────────────────────────────────────────────────────────
    def _enrich(self, algo_days, destination, events_ctx, weather_ctx,
                interests_str, travelers, day_dates, trip_start, daily_total_cap):

        # Build compact schedule summary for LLM
        summary = ""
        for day in algo_days:
            summary += "\nDay " + str(day["day"]) + " — " + day.get("date_label","") + ":\n"
            summary += "  Weather: " + day.get("weather_note","") + "\n"
            for act in day.get("activities", []):
                prefix = "[MEAL] " if act.get("is_meal") else ""
                summary += ("  " + act.get("time","") + " " + prefix +
                            act.get("activity","") +
                            (" | " + act.get("travel_note","") if act.get("travel_note") else "") + "\n")
            summary += "  Total cost: Rs " + str(int(day.get("estimated_cost_inr",0))) + "\n"

        system_prompt = (
            "You are a travel writer. The schedule, timings, costs, and routing are FIXED. "
            "Do NOT change any times, costs, or activity order. "
            "Only add: engaging day title with date, 2-sentence narrative per activity, "
            "tips, and event detection. Return ONLY valid JSON array."
        )
        user_prompt = (
            "Enrich this pre-computed itinerary for " + destination + ".\n\n"
            "=== FIXED SCHEDULE (do not alter timings, costs, or order) ===\n" +
            summary + "\n\n"
            "=== LOCAL EVENTS ===\n" + events_ctx + "\n\n"
            "=== WEATHER ===\n" + weather_ctx + "\n\n"
            "Interests: " + interests_str + " | Travelers: " + str(travelers) + "\n\n"
            "Return JSON array of " + str(len(algo_days)) + " objects. Each must have:\n"
            "  day (number, keep as-is)\n"
            "  title (string — include actual date e.g. 'Day 1 — April 01, 2026 (Wednesday)')\n"
            "  weather_note (string — keep from schedule above)\n"
            "  activities (array — keep ALL items, each with these EXACT keys:\n"
            "    time (string), activity (string — the place/meal name), description (string),\n"
            "    location (string), duration (string), cost_inr (number),\n"
            "    is_meal (bool), travel_note (string), caution (string))\n"
            "  meals (object: {breakfast: string, lunch: string, dinner: string})\n"
            "  estimated_cost_inr (NUMBER — keep EXACTLY as in schedule, do not change)\n"
            "  tips (string — one practical tip)\n"
            "  has_event (bool), event_name (string or null)\n\n"
            "CRITICAL: In activities, use key 'activity' (not 'name') for the place name.\n"
            "Return ONLY the JSON array."
        )

        response = self.clean_json(self.invoke(system_prompt, user_prompt))
        try:
            enriched = json.loads(response)
            # Re-stamp authoritative values from algo_days
            for i, day in enumerate(enriched):
                if i < len(algo_days):
                    src = algo_days[i]
                    day["actual_date"] = src.get("actual_date","")
                    day["date_label"]  = src.get("date_label", day_dates[i] if i < len(day_dates) else "")
                    try:
                        orig = float(src.get("estimated_cost_inr", 0) or 0)
                        # Report the actual estimated spend, even when it exceeds
                        # the suggested budget. The scheduler attaches a warning.
                        day["estimated_cost_inr"] = round(orig, 2)
                    except (ValueError, TypeError):
                        day["estimated_cost_inr"] = 0.0
                    # Always restore authoritative activity data from algo_days.
                    # The LLM may rename "activity" to "name" or drop fields —
                    # we overlay the original field values to guarantee correctness.
                    src_acts = src.get("activities", [])
                    llm_acts = day.get("activities", [])
                    if not llm_acts:
                        # LLM returned no activities at all — use algo_days directly
                        day["activities"] = src_acts
                    else:
                        # Merge: keep LLM description but restore all structural fields
                        merged = []
                        for j, src_act in enumerate(src_acts):
                            if j < len(llm_acts):
                                llm_act = llm_acts[j]
                                merged.append({
                                    # Structural fields — always from algo_days (authoritative)
                                    "time":        src_act.get("time", ""),
                                    "activity":    src_act.get("activity", ""),  # place name
                                    "location":    src_act.get("location", ""),
                                    "duration":    src_act.get("duration", ""),
                                    "cost_inr":    src_act.get("cost_inr", 0),
                                    "is_meal":     src_act.get("is_meal", False),
                                    "meal_type":   src_act.get("meal_type", ""),
                                    "travel_note": src_act.get("travel_note", ""),
                                    "caution":     src_act.get("caution", ""),
                                    # Narrative — from LLM (enriched)
                                    "description": llm_act.get("description",
                                                    src_act.get("description", "")),
                                })
                            else:
                                merged.append(src_act)
                        day["activities"] = merged
            return enriched
        except json.JSONDecodeError as e:
            print("JSON error (enrich): " + str(e) + " — returning raw algo days")
            for i, day in enumerate(algo_days):
                if i < len(day_dates):
                    day.setdefault("title", "Day " + str(day["day"]) + " — " + day_dates[i])
                    day.setdefault("tips", "Enjoy your day!")
                    day.setdefault("has_event", False)
                    day.setdefault("event_name", None)
            return algo_days

    # ── PATH B ────────────────────────────────────────────────────────────────
    def _llm_generate(self, destination, duration, interests_str, travelers,
                       raw_start, day_dates, days_until, season, weather_ctx,
                       events_ctx, places, restaurants, daily_total_cap,
                       daily_food, meal_pp, act_per_day, trip_start):

        places_summary = "\n".join(
            "- " + p.get("name","") + " [" + p.get("category","") + "]"
            " opens " + p.get("open_time","09:00") + " closes " + p.get("close_time","18:00") +
            " | outdoor=" + str(p.get("is_outdoor",True)) +
            " | entry Rs " + str(int(p.get("entry_fee_inr",0)))
            for p in places[:12]
        ) if places else "No places data"

        rest_summary = "\n".join(
            "- " + r.get("name","") + " [" + r.get("cuisine","") + "] Rs " +
            str(int(r.get("avg_cost_per_person_inr",300))) + "/person"
            for r in restaurants[:8]
        ) if restaurants else "No restaurant data"

        date_sched = "\n".join("  Day " + str(i+1) + " → " + day_dates[i]
                               for i in range(duration))

        user_prompt = (
            "Create a " + str(duration) + "-day itinerary for " + destination + ".\n\n"
            "Start: " + raw_start + "\nCalendar:\n" + date_sched +
            "\nSeason: " + season + " | Days until trip: " + str(days_until) + "\n\n"
            "=== WEATHER ===\n" + weather_ctx + "\n\n"
            "=== LOCAL EVENTS ===\n" + events_ctx + "\n\n"
            "=== PLACES ===\n" + places_summary + "\n\n"
            "=== RESTAURANTS ===\n" + rest_summary + "\n\n"
            "Travelers: " + str(travelers) + " | Interests: " + interests_str + "\n\n"
            "Daily budget cap: Rs " + str(int(daily_total_cap)) + "\n"
            "Max meal per person: Rs " + str(int(meal_pp)) + "\n\n"
            "Return JSON array of " + str(duration) + " day objects, each with:\n"
            "day, title (include actual date), weather_note, "
            "activities (array: time, activity, description, location, duration, cost_inr), "
            "meals (breakfast/lunch/dinner), estimated_cost_inr (actual estimated total; "
            "may exceed the suggested budget), "
            "tips, has_event (bool), event_name.\nReturn ONLY the JSON array."
        )

        response = self.clean_json(self.invoke(
            "You are a practical travel planner. Treat budget and weather as advisory warnings, "
            "not reasons to omit otherwise suitable attractions. Never falsify or cap cost estimates. "
            "All costs in INR. Return ONLY valid JSON array.",
            user_prompt))
        try:
            days = json.loads(response)
            for i, day in enumerate(days):
                if i < len(day_dates):
                    day["actual_date"] = (trip_start + timedelta(days=i)).isoformat()
                    day["date_label"]  = day_dates[i]
            for day in days:
                try:
                    cost = float(day.get("estimated_cost_inr", 0) or 0)
                    day["estimated_cost_inr"] = round(cost, 2)
                    for act in day.get("activities", []):
                        try:
                            act["cost_inr"] = round(float(act.get("cost_inr", 0) or 0), 2)
                        except (ValueError, TypeError):
                            act["cost_inr"] = 0
                except (ValueError, TypeError):
                    day["estimated_cost_inr"] = 0.0
            return days
        except json.JSONDecodeError as e:
            print("JSON error (llm_generate): " + str(e))
            return []
