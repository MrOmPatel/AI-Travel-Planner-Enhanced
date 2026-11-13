from typing import TypedDict
from langgraph.graph import StateGraph, END
from agents.extraction_agent import ExtractionAgent
from agents.place_agent import PlaceAgent
from agents.restaurants_agent import RestaurantsAgent
from agents.hotels_agent import HotelsAgent
from agents.itinerary_agent import ItineraryAgent
from agents.weather_agent import WeatherAgent
from budget_allocator import allocate
from algorithms import run_algorithm_pipeline
from helper import geocode_city


class TravelPlanState(TypedDict):
    user_input:       str
    travel_details:   dict
    places:           list
    restaurants:      list
    hotels:           list
    weather:          dict
    algo_days:        list
    itinerary:        list
    budget_breakdown: dict
    error:            str | None


class TravelPlanWorkflow:

    def __init__(self):
        self.extraction_agent  = ExtractionAgent()
        self.places_agent      = PlaceAgent()
        self.restaurants_agent = RestaurantsAgent()
        self.hotels_agent      = HotelsAgent()
        self.itinerary_agent   = ItineraryAgent()
        self.weather_agent     = WeatherAgent()
        self.workflow          = self._build_workflow()

    def _build_workflow(self):
        wf = StateGraph(TravelPlanState)
        wf.add_node("extract",          self._extract_node)
        wf.add_node("fetch_weather",    self._weather_node)
        wf.add_node("find_places",      self._places_node)
        wf.add_node("find_restaurants", self._restaurants_node)
        wf.add_node("find_hotels",      self._hotels_node)
        wf.add_node("run_algorithms",   self._algorithms_node)
        wf.add_node("create_itinerary", self._itinerary_node)
        wf.set_entry_point("extract")
        wf.add_edge("extract",          "fetch_weather")
        wf.add_edge("fetch_weather",    "find_places")
        wf.add_edge("find_places",      "find_restaurants")
        wf.add_edge("find_restaurants", "find_hotels")
        wf.add_edge("find_hotels",      "run_algorithms")
        wf.add_edge("run_algorithms",   "create_itinerary")
        wf.add_edge("create_itinerary", END)
        return wf.compile()

    # ── Nodes ─────────────────────────────────────────────────────────────────
    def _extract_node(self, state):
        print("Extracting travel details...")
        try:
            state["travel_details"] = self.extraction_agent.extract_details(state["user_input"])
            td = state["travel_details"]
            print("Extracted: " + td.get("destination", "?") +
                  " | Budget: Rs " + str(td.get("budget_inr", 0)))
        except Exception as e:
            print("Extraction error: " + str(e))
            state["error"] = str(e)
        return state

    def _weather_node(self, state):
        print("Fetching live weather...")
        try:
            td = state["travel_details"]
            state["weather"] = self.weather_agent.get_weather(
                td.get("destination", ""),
                td.get("duration", 5),
                start_date=td.get("start_date")   # pass trip start date
            )
        except Exception as e:
            print("Weather error: " + str(e))
            state["weather"] = {"data_available": False}
        return state

    def _places_node(self, state):
        print("Finding places (budget-constrained)...")
        try:
            state["places"] = self.places_agent.find_places(state["travel_details"])
            print("Found " + str(len(state["places"])) + " places")
        except Exception as e:
            print("Places error: " + str(e))
            state["places"] = []
        return state

    def _restaurants_node(self, state):
        print("Finding restaurants (budget-constrained)...")
        try:
            state["restaurants"] = self.restaurants_agent.find_restaurants(state["travel_details"])
            print("Found " + str(len(state["restaurants"])) + " restaurants")
        except Exception as e:
            print("Restaurants error: " + str(e))
            state["restaurants"] = []
        return state

    def _hotels_node(self, state):
        print("Finding hotels (budget-constrained)...")
        try:
            state["hotels"] = self.hotels_agent.find_hotels(state["travel_details"])
            print("Found " + str(len(state["hotels"])) + " hotels")
        except Exception as e:
            print("Hotels error: " + str(e))
            state["hotels"] = []
        return state

    def _algorithms_node(self, state):
        """Run all 7 deterministic algorithms on gathered data."""
        print("Running 7 algorithms (Scoring → K-Means → TSP → Scheduler)...")
        try:
            td = state["travel_details"]
            env = allocate(
                float(td.get("budget_inr", 80000)),
                int(td.get("duration", 5)),
                int(td.get("travelers", 2)),
                td.get("travel_type", "default")
            )
            # Extract hotel coordinates — hotel is the TSP start point each day
            hotels = state.get("hotels", [])
            hotel_lat, hotel_lon = 0.0, 0.0

            # Step 1: try cheapest hotel's LLM-provided lat/lon
            if hotels:
                try:
                    lat = float(hotels[0].get("lat") or 0)
                    lon = float(hotels[0].get("lon") or 0)
                    if lat != 0.0 and lon != 0.0:
                        hotel_lat, hotel_lon = lat, lon
                        print("Hotel coords from LLM: " + str(hotel_lat) + ", " + str(hotel_lon))
                except (ValueError, TypeError):
                    pass

            # Step 2: if hotel had no coords, geocode the city center as fallback
            if hotel_lat == 0.0 and hotel_lon == 0.0:
                print("Hotel has no coordinates — geocoding city center as TSP start point")
                hotel_lat, hotel_lon = geocode_city(td.get("destination", ""))

            td["hotel_lat"] = hotel_lat
            td["hotel_lon"] = hotel_lon
            print("TSP start point: (" + str(hotel_lat) + ", " + str(hotel_lon) + ")")
            state["algo_days"] = run_algorithm_pipeline(
                places         = state.get("places", []),
                restaurants    = state.get("restaurants", []),
                travel_details = td,
                weather        = state.get("weather", {}),
                env            = env,
            )
            print("Algorithms complete — " + str(len(state["algo_days"])) + " days computed")
        except Exception as e:
            print("Algorithm error: " + str(e))
            import traceback; traceback.print_exc()
            state["algo_days"] = []
        return state

    def _itinerary_node(self, state):
        print("Creating budget-enforced itinerary...")
        try:
            state["itinerary"] = self.itinerary_agent.create_itinerary(
                state["travel_details"], state["places"],
                state["restaurants"], state["weather"],
                algo_days=state.get("algo_days") or []
            )
            print("Created " + str(len(state["itinerary"])) + "-day itinerary")
            state["budget_breakdown"] = self._calculate_budget(state)
        except Exception as e:
            print("Itinerary error: " + str(e))
            state["itinerary"] = []
        return state

    # ── Budget breakdown — uses actual clamped values from data ───────────────
    def _calculate_budget(self, state) -> dict:
        td          = state.get("travel_details", {})
        budget_inr  = float(td.get("budget_inr", 80000))
        duration    = int(td.get("duration", 5))
        travelers   = int(td.get("travelers", 2))
        travel_type = td.get("travel_type", "default")

        # Get the planned envelopes
        env = allocate(budget_inr, duration, travelers, travel_type)

        hotels    = state.get("hotels", [])
        itinerary = state.get("itinerary", [])
        places    = state.get("places", [])

        # Accommodation: use cheapest hotel total (already clamped)
        hotel_totals = [float(h.get("total_estimated_inr", 0))
                        for h in hotels if h.get("total_estimated_inr")]
        accommodation = min(hotel_totals) if hotel_totals else env["accommodation_total"]

        # Food: sum actual itinerary day costs (already clamped), take food portion
        total_daily_costs = sum(
            float(day.get("estimated_cost_inr", 0) or 0) for day in itinerary
        )
        # Estimate food as 60% of daily costs (activities are the rest)
        food = min(round(total_daily_costs * 0.60, 2), env["food_total"])

        # Activities: sum of actual entry fees from places (already clamped)
        activities = min(
            sum(float(p.get("entry_fee_inr", 0)) for p in places),
            env["activities_total"]
        )

        transport = env["transport_total"]
        misc      = env["misc_total"]

        total     = round(accommodation + food + activities + transport + misc, 2)
        # Hard ceiling: total can never exceed 95% of budget
        total     = min(total, env["usable_inr"])
        remaining = round(budget_inr - total, 2)

        return {
            "accommodation":      round(accommodation, 2),
            "food":               round(food, 2),
            "activities":         round(activities, 2),
            "transportation":     round(transport, 2),
            "miscellaneous":      round(misc, 2),
            "total_estimated":    total,
            "user_budget_inr":    budget_inr,
            "user_budget_usd":    td.get("budget_usd", 0),
            "inr_rate":           td.get("inr_rate", 84.0),
            "remaining":          remaining,
            "within_budget":      remaining >= 0,
            # Envelopes for display
            "envelope": {
                "hotel_max_per_night":     env["hotel_max_per_night"],
                "meal_budget_per_person":  env["meal_budget_per_person"],
                "activities_per_day":      env["activities_per_day"],
            }
        }

    # ── Re-optimize a single day ──────────────────────────────────────────────
    def reoptimize_day(self, day_number: int, removed_attraction: str,
                       travel_details: dict, places: list,
                       restaurants: list, weather: dict,
                       used_places: list = None) -> dict:
        """
        Re-optimise a single day without repeating places from other days.

        used_places: list of place names already scheduled on OTHER days.
                     These are excluded before running the algorithm so the
                     re-optimised day gets fresh attractions.
        """
        print("Re-optimizing day " + str(day_number) +
              " (removed: " + removed_attraction + ")")

        # Exclude: the removed attraction + places used on other days
        excluded = set()
        excluded.add(removed_attraction)
        if used_places:
            excluded.update(used_places)

        available = [p for p in places if p.get("name", "") not in excluded]
        print("  Available places after exclusion: " + str(len(available)) +
              " / " + str(len(places)))

        try:
            env = allocate(
                float(travel_details.get("budget_inr", 80000)),
                int(travel_details.get("duration", 5)),
                int(travel_details.get("travelers", 2)),
                travel_details.get("travel_type", "default")
            )
            # Run pipeline only for this one day
            # Temporarily set duration=1 so clustering makes one group
            single_day_details = dict(travel_details)
            single_day_details["duration"] = 1
            # Shift start_date to the correct day
            from datetime import date, timedelta
            raw_start = travel_details.get("start_date") or date.today().isoformat()
            try:
                trip_start = date.fromisoformat(raw_start)
            except ValueError:
                trip_start = date.today()
            day_date = trip_start + timedelta(days=day_number - 1)
            single_day_details["start_date"] = day_date.isoformat()

            algo_days = run_algorithm_pipeline(
                available, restaurants, single_day_details, weather, env
            )
        except Exception as e:
            print("Algorithm error in reoptimize: " + str(e))
            import traceback; traceback.print_exc()
            algo_days = []

        full = self.itinerary_agent.create_itinerary(
            travel_details, available, restaurants, weather,
            algo_days=algo_days
        )
        if full:
            result = full[0]   # single day pipeline always returns index 0
            result["day"] = day_number   # stamp with correct day number
            return result
        return {}

    # ── Main entry ────────────────────────────────────────────────────────────
    def plan_travel(self, user_input: str) -> dict:
        print("Starting travel planning workflow...")
        initial_state = {
            "user_input": user_input, "travel_details": {}, "places": [],
            "restaurants": [], "hotels": [], "weather": {},
            "algo_days": [], "itinerary": [], "budget_breakdown": {}, "error": None
        }
        final = self.workflow.invoke(initial_state)
        print("Workflow complete!")
        return {
            "travel_details":   final.get("travel_details", {}),
            "places":           final.get("places", []),
            "restaurants":      final.get("restaurants", []),
            "hotels":           final.get("hotels", []),
            "weather":          final.get("weather", {}),
            "itinerary":        final.get("itinerary", []),
            "budget_breakdown": final.get("budget_breakdown", {}),
            "error":            final.get("error"),
        }
