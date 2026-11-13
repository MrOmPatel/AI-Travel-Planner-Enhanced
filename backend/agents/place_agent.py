import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from .base_agent import BaseAgent
from helper import Helper
from budget_allocator import allocate
from tavily import TavilyClient


class PlaceAgent(BaseAgent):
    """Find attractions with entry fees capped within the activities envelope."""

    def __init__(self):
        super().__init__()
        tavily_key = os.getenv("TAVILY_API_KEY")
        self.tavily = TavilyClient(api_key=tavily_key) if tavily_key else None
        self.helper = Helper()

    def find_places(self, travel_details: dict) -> list:
        destination = travel_details.get("destination", "Unknown")
        budget_inr  = float(travel_details.get("budget_inr", 80000))
        duration    = int(travel_details.get("duration", 5))
        travelers   = int(travel_details.get("travelers", 2))
        interests   = travel_details.get("interests", [])
        travel_type = travel_details.get("travel_type", "default")
        interests_str = ", ".join(interests)

        env = allocate(budget_inr, duration, travelers, travel_type)
        max_entry_fee  = env["max_entry_fee_per_place"]   # per place per person
        act_per_day    = env["activities_per_day"]
        act_total      = env["activities_total"]

        search_results = []
        if self.tavily:
            try:
                query = "top tourist attractions in " + destination + " " + " ".join(interests[:3])
                resp  = self.tavily.search(query, max_results=5)
                search_results = resp.get("results", [])
            except Exception as e:
                print("Tavily error (places): " + str(e))

        web_ctx = "\n".join(
            "- " + r.get("title", "") + ": " + r.get("content", "")[:200]
            for r in search_results[:5]
        ) if search_results else "No web data"

        system_prompt = (
            "You are a local travel expert. Use web results for accuracy. "
            "STRICT RULE: entry_fee_inr for every place MUST be below the ceiling given. "
            "Prefer free or low-cost attractions. "
            "Return ONLY valid JSON array, nothing else."
        )
        user_prompt = (
            "Create must-visit places list in " + destination + " for " + str(duration) + " days.\n\n"
            "Web Search:\n" + web_ctx + "\n\n"
            "Interests: " + interests_str + "\n\n"
            "=== HARD BUDGET CONSTRAINTS ===\n"
            "Total activities budget: Rs " + str(int(act_total)) + "\n"
            "Activities budget per day: Rs " + str(int(act_per_day)) + "\n"
            "Max entry fee per place per person: Rs " + str(int(max_entry_fee)) + "\n"
            "Prefer FREE attractions. Include paid ones only if genuinely unmissable.\n"
            "Do NOT include any place with entry_fee_inr above Rs " + str(int(max_entry_fee)) + ".\n\n"
            "Return JSON array of 8-10 places. Each must have:\n"
            "name, description (2-3 sentences), category, location, how_to_reach,\n"
            "best_time (morning/afternoon/evening), visit_duration_hrs (number),\n"
            "entry_fee_inr (NUMBER, 0 if free, max Rs " + str(int(max_entry_fee)) + "),\n"
            "is_outdoor (true/false), open_time (HH:MM), close_time (HH:MM),\n"
            "rating (3.5-5.0), tips (one helpful tip), tags (array of strings),\n"
            "lat (decimal latitude of this place, e.g. 26.9855),\n"
            "lon (decimal longitude of this place, e.g. 75.8513).\n"
            "IMPORTANT: lat and lon must be real GPS coordinates for " + destination + ".\n\n"
            "Return ONLY the JSON array."
        )

        response = self.clean_json(self.invoke(system_prompt, user_prompt))
        try:
            places = json.loads(response)
            for i, place in enumerate(places):
                # Parse and CLAMP entry fee
                try:
                    fee = float(place.get("entry_fee_inr", 0) or 0)
                    fee = min(fee, max_entry_fee)
                    place["entry_fee_inr"] = round(fee, 2)
                except (ValueError, TypeError):
                    place["entry_fee_inr"] = 0

                # Validate and normalise lat/lon
                try:
                    place["lat"] = float(place.get("lat") or 0)
                    place["lon"] = float(place.get("lon") or 0)
                    # Sanity check: if both are 0 the LLM forgot, log it
                    if place["lat"] == 0.0 and place["lon"] == 0.0:
                        print("WARNING: " + place.get("name","?") + " has no coordinates")
                except (ValueError, TypeError):
                    place["lat"] = 0.0
                    place["lon"] = 0.0

                place_name = place.get("name", "")
                img_q = place_name + " " + destination + " landmark"
                # use_wikipedia=True → tries real Wikipedia photo first
                place["image_url"] = self.helper.search_images(
                    img_q,
                    place_name=place_name,
                    use_wikipedia=True
                )[0]
                place["maps_link"] = self.helper.get_maps_link(place.get("name", ""), destination)
                if i < len(search_results) and "url" in search_results[i]:
                    place["source_url"] = search_results[i]["url"]

            # Sort free/cheap first
            places.sort(key=lambda x: x.get("entry_fee_inr", 0))
            return places
        except json.JSONDecodeError as e:
            print("JSON decode error (places): " + str(e))
            return []
