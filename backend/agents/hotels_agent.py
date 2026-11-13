import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from .base_agent import BaseAgent
from helper import Helper
from budget_allocator import allocate
from tavily import TavilyClient


class HotelsAgent(BaseAgent):
    """Find hotels strictly within the accommodation envelope."""

    def __init__(self):
        super().__init__()
        tavily_key = os.getenv("TAVILY_API_KEY")
        self.tavily = TavilyClient(api_key=tavily_key) if tavily_key else None
        self.helper = Helper()

    def find_hotels(self, travel_details: dict) -> list:
        destination = travel_details.get("destination", "Unknown")
        budget_inr  = float(travel_details.get("budget_inr", 80000))
        duration    = int(travel_details.get("duration", 5))
        travelers   = int(travel_details.get("travelers", 2))
        travel_type = travel_details.get("travel_type", "default")

        # Hard ceilings from allocator
        env = allocate(budget_inr, duration, travelers, travel_type)
        max_per_night = env["hotel_max_per_night"]
        acc_total     = env["accommodation_total"]

        search_results = []
        if self.tavily:
            try:
                resp = self.tavily.search(
                    "budget hotels under Rs " + str(int(max_per_night)) +
                    " per night in " + destination, max_results=5)
                search_results = resp.get("results", [])
            except Exception as e:
                print("Tavily error (hotels): " + str(e))

        web_ctx = "\n".join(
            "- " + r.get("title", "") + ": " + r.get("content", "")[:200]
            for r in search_results[:5]
        ) if search_results else "No web data"

        system_prompt = (
            "You are a hotel expert. STRICT RULE: every hotel you list MUST have "
            "price_per_night_inr BELOW the ceiling given. Never exceed it. "
            "Return ONLY valid JSON array, nothing else."
        )
        user_prompt = (
            "Recommend hotels in " + destination + " for " + str(travelers) +
            " travelers, " + str(duration) + " nights.\n\n"
            "Web Search:\n" + web_ctx + "\n\n"
            "=== HARD BUDGET CONSTRAINTS ===\n"
            "Total accommodation envelope: Rs " + str(int(acc_total)) + "\n"
            "MAXIMUM price per night: Rs " + str(int(max_per_night)) + "\n"
            "You MUST NOT suggest any hotel above Rs " + str(int(max_per_night)) + "/night.\n"
            "Prefer budget and mid-range options.\n\n"
            "Return JSON array of 4-5 hotels, cheapest first. Each must have:\n"
            "name, category (Budget/3-Star/4-Star),\n"
            "description (2-3 sentences),\n"
            "location (neighbourhood),\n"
            "price_per_night_inr (NUMBER, MUST be <= " + str(int(max_per_night)) + "),\n"
            "total_estimated_inr (price_per_night_inr x " + str(duration) + "),\n"
            "rating (3.5-5.0), amenities (array), room_type, proximity, booking_tip,\n"
            "lat (decimal latitude of hotel area, e.g. 26.9124),\n"
            "lon (decimal longitude of hotel area, e.g. 75.7873).\n"
            "IMPORTANT: lat and lon must be real GPS coordinates for " + destination + ".\n\n"
            "Return ONLY the JSON array."
        )

        response = self.clean_json(self.invoke(system_prompt, user_prompt))
        try:
            hotels = json.loads(response)
            for i, h in enumerate(hotels):
                # Parse and CLAMP price to ceiling
                try:
                    ppn = float(h.get("price_per_night_inr", max_per_night) or max_per_night)
                    ppn = min(ppn, max_per_night)              # hard clamp
                    h["price_per_night_inr"] = round(ppn, 2)
                    h["total_estimated_inr"] = round(ppn * duration, 2)
                except (ValueError, TypeError):
                    h["price_per_night_inr"] = round(max_per_night * 0.7, 2)
                    h["total_estimated_inr"] = round(h["price_per_night_inr"] * duration, 2)

                # Validate and normalise lat/lon
                try:
                    h["lat"] = float(h.get("lat") or 0)
                    h["lon"] = float(h.get("lon") or 0)
                    if h["lat"] == 0.0 and h["lon"] == 0.0:
                        print("WARNING: hotel " + h.get("name","?") + " has no coordinates")
                except (ValueError, TypeError):
                    h["lat"] = 0.0
                    h["lon"] = 0.0

                img_q = h.get("name", "") + " " + destination + " hotel"
                # use_wikipedia=False — hotels are not on Wikipedia
                h["image_url"] = self.helper.search_images(img_q)[0]
                h["maps_link"] = self.helper.get_maps_link(h.get("name", ""), destination)
                if i < len(search_results) and "url" in search_results[i]:
                    h["source_url"] = search_results[i]["url"]

            # Sort cheapest first so frontend shows affordable option first
            hotels.sort(key=lambda x: x.get("price_per_night_inr", 0))
            return hotels
        except json.JSONDecodeError as e:
            print("JSON decode error (hotels): " + str(e))
            return []
