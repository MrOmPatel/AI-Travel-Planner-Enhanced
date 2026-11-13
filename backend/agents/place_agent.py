import json
import os
import sys

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

    @staticmethod
    def _parse_places(raw_response):
        """Accept either the expected {places: [...]} object or a legacy array."""
        cleaned = BaseAgent.clean_json(raw_response)
        data = json.loads(cleaned)
        if isinstance(data, dict):
            data = data.get("places", data.get("attractions", []))
        if not isinstance(data, list):
            raise ValueError("The places response must contain a JSON array.")
        return [item for item in data if isinstance(item, dict) and item.get("name")]

    def find_places(self, travel_details: dict) -> list:
        destination = travel_details.get("destination", "Unknown")
        budget_inr = float(travel_details.get("budget_inr", 80000))
        duration = int(travel_details.get("duration", 5))
        travelers = int(travel_details.get("travelers", 2))
        interests = travel_details.get("interests", [])
        travel_type = travel_details.get("travel_type", "default")
        interests_str = ", ".join(interests)

        env = allocate(budget_inr, duration, travelers, travel_type)
        max_entry_fee = env["max_entry_fee_per_place"]
        act_per_day = env["activities_per_day"]
        act_total = env["activities_total"]

        search_results = []
        if self.tavily:
            try:
                query = "top tourist attractions in " + destination + " " + " ".join(interests[:3])
                resp = self.tavily.search(query, max_results=5)
                search_results = resp.get("results", [])
            except Exception as e:
                print("Tavily error (places): " + str(e))

        web_ctx = "\\n".join(
            "- " + r.get("title", "") + ": " + r.get("content", "")[:200]
            for r in search_results[:5]
        ) if search_results else "No web data"

        system_prompt = (
            "You are a local travel expert. Use the supplied web results where relevant. "
            "Return a single valid JSON object with a top-level key named places. "
            "The value of places must be an array. Do not use markdown or comments. "
            "Use double quotes for every JSON key and string. Do not add trailing commas. "
            "Do not invent attractions outside the requested destination. "
            "Keep each description and tip concise so the complete response fits."
        )
        user_prompt = (
            "Create a list of 8-10 must-visit attractions in " + destination + " for "
            + str(duration) + " days.\n\n"
            "Web Search:\\n" + web_ctx + "\\n\\n"
            "Interests: " + interests_str + "\\n\\n"
            "BUDGET CONSTRAINTS:\\n"
            "Total activities budget: Rs " + str(int(act_total)) + "\\n"
            "Activities budget per day: Rs " + str(int(act_per_day)) + "\\n"
            "Maximum entry fee per place per person: Rs " + str(int(max_entry_fee)) + "\\n"
            "Prefer free or low-cost attractions. Never return a fee above the maximum. "
            "Use 0 for free attractions.\n\n"
            "Return this exact structure: {\\\"places\\\":[ ... ]}. "
            "Each place object must contain these fields: "
            "name, description (1-2 concise sentences), category, location, how_to_reach, "
            "best_time (morning/afternoon/evening), visit_duration_hrs (number), "
            "entry_fee_inr (number), is_outdoor (boolean), open_time (HH:MM), "
            "close_time (HH:MM), rating (number), tips (short string), tags (array of strings), "
            "lat (number), lon (number). "
            "Coordinates must be real decimal GPS coordinates for " + destination + ". "
            "Ensure the JSON is complete and syntactically valid."
        )

        # JSON mode prevents malformed syntax. Retry once with a smaller, explicit repair
        # request if the provider/model still returns an unparsable response.
        places = None
        first_error = None
        try:
            raw = self.invoke_json(system_prompt, user_prompt)
            places = self._parse_places(raw)
        except Exception as e:
            first_error = e
            print("Places JSON attempt 1 failed: " + str(e))

        if not places:
            try:
                retry_prompt = (
                    user_prompt
                    + "\\n\\nIMPORTANT RETRY: Return a compact JSON object only: "
                    + "{\\\"places\\\":[...]} with 8-10 attractions. "
                    + "Use short descriptions and tips. No markdown, no trailing commas."
                )
                raw = self.invoke_json(system_prompt, retry_prompt)
                places = self._parse_places(raw)
            except Exception as e:
                print("Places JSON attempt 2 failed: " + str(e))
                if first_error is not None:
                    print("Initial places parsing/provider error: " + str(first_error))
                return []

        if not places:
            print("Places response parsed successfully but contained no valid named places.")
            return []

        for i, place in enumerate(places):
            try:
                fee = float(place.get("entry_fee_inr", 0) or 0)
                place["entry_fee_inr"] = round(max(0, min(fee, max_entry_fee)), 2)
            except (ValueError, TypeError):
                place["entry_fee_inr"] = 0

            try:
                place["lat"] = float(place.get("lat") or 0)
                place["lon"] = float(place.get("lon") or 0)
                if place["lat"] == 0.0 and place["lon"] == 0.0:
                    print("WARNING: " + place.get("name", "?") + " has no coordinates")
            except (ValueError, TypeError):
                place["lat"] = 0.0
                place["lon"] = 0.0

            place_name = str(place.get("name", "")).strip()
            img_q = place_name + " " + destination + " landmark"
            try:
                images = self.helper.search_images(
                    img_q, place_name=place_name, use_wikipedia=True
                )
                place["image_url"] = images[0] if images else ""
            except Exception as e:
                print("Image lookup failed for " + place_name + ": " + str(e))
                place["image_url"] = ""

            try:
                place["maps_link"] = self.helper.get_maps_link(place_name, destination)
            except Exception as e:
                print("Maps link failed for " + place_name + ": " + str(e))
                place["maps_link"] = ""

            if i < len(search_results) and search_results[i].get("url"):
                place["source_url"] = search_results[i]["url"]

        places.sort(key=lambda x: x.get("entry_fee_inr", 0))
        print("Found " + str(len(places)) + " places")
        return places
