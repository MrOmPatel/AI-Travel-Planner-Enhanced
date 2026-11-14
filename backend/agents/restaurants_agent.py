import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from .base_agent import BaseAgent
from helper import Helper
from budget_allocator import allocate
from tavily import TavilyClient


class RestaurantsAgent(BaseAgent):
    """Find restaurants strictly within the food envelope."""

    def __init__(self):
        super().__init__()
        tavily_key = os.getenv("TAVILY_API_KEY")
        self.tavily = TavilyClient(api_key=tavily_key) if tavily_key else None
        self.helper = Helper()

    def find_restaurants(self, travel_details: dict) -> list:
        destination = travel_details.get("destination", "Unknown")
        budget_inr  = float(travel_details.get("budget_inr", 80000))
        duration    = int(travel_details.get("duration", 5))
        travelers   = int(travel_details.get("travelers", 2))
        interests   = travel_details.get("interests", [])
        travel_type = travel_details.get("travel_type", "default")
        interests_str = ", ".join(interests)

        env = allocate(budget_inr, duration, travelers, travel_type)
        meal_budget   = env["meal_budget_per_person"]     # per person per meal
        food_per_day  = env["food_per_day"]               # total food budget per day
        food_total    = env["food_total"]

        search_results = []
        if self.tavily:
            try:
                resp = self.tavily.search(
                    "affordable restaurants local food in " + destination, max_results=5)
                search_results = resp.get("results", [])
            except Exception as e:
                print("Tavily error (restaurants): " + str(e))

        web_ctx = "\n".join(
            "- " + r.get("title", "") + ": " + r.get("content", "")[:200]
            for r in search_results[:5]
        ) if search_results else "No web data"

        system_prompt = (
            "You are a food expert. Recommend a useful range of restaurants, prioritising "
            "options that fit the user's budget but include other relevant choices when useful. "
            "Never falsify or clamp price estimates. Return ONLY valid JSON array."
        )
        user_prompt = (
            "Recommend restaurants in " + destination + " for " + str(travelers) +
            " travelers.\n\n"
            "Web Search:\n" + web_ctx + "\n\n"
            "=== BUDGET GUIDELINE (not a hard filter) ===\\n"
            "Food budget per day: Rs " + str(int(food_per_day)) + "\\n"
            "Suggested per-person per-meal budget: Rs " + str(int(meal_budget)) + "\\n"
            "Prioritise affordable places, but do not hide useful options above this amount.\\n\\n"
            "Preferences: " + interests_str + "\n\n"
            "Return JSON array of 6-8 restaurants. Each must have:\n"
            "name, cuisine, description (2-3 sentences, must-try dishes),\n"
            "budget_level (Budget/Mid-range only),\n"
            "avg_cost_per_person_inr (realistic NUMBER estimate, may exceed guideline),\n"
            "location, rating (3.5-5.0), specialties (array), atmosphere,\n"
            "best_time (breakfast/lunch/dinner/both), reservation_needed (true/false).\n\n"
            "Return ONLY the JSON array."
        )

        response = self.clean_json(self.invoke(system_prompt, user_prompt))
        try:
            restaurants = json.loads(response)
            for i, r in enumerate(restaurants):
                # Parse realistic estimated cost; retain above-guideline prices
                try:
                    cost = float(r.get("avg_cost_per_person_inr", meal_budget) or meal_budget)
                    r["avg_cost_per_person_inr"] = round(max(0, cost), 2)
                    r["over_budget_guideline"] = cost > meal_budget
                except (ValueError, TypeError):
                    r["avg_cost_per_person_inr"] = round(meal_budget * 0.8, 2)

                img_q = r.get("name", "") + " " + destination + " restaurant"
                # use_wikipedia=False — restaurants are not on Wikipedia
                r["image_url"] = self.helper.search_images(img_q)[0]
                r["maps_link"] = self.helper.get_maps_link(r.get("name", ""), destination)
                if i < len(search_results) and "url" in search_results[i]:
                    r["source_url"] = search_results[i]["url"]

            # Sort cheapest first
            restaurants.sort(key=lambda x: x.get("avg_cost_per_person_inr", 0))
            return restaurants
        except json.JSONDecodeError as e:
            print("JSON decode error (restaurants): " + str(e))
            return []
