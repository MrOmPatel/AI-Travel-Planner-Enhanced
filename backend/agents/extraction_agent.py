import json
import re
import requests
from datetime import date, timedelta
from .base_agent import BaseAgent

EXCHANGE_URL = "https://open.er-api.com/v6/latest/USD"


def _live_inr_rate() -> float:
    try:
        r = requests.get(EXCHANGE_URL, timeout=5)
        if r.status_code == 200:
            return float(r.json().get("rates", {}).get("INR", 84.0))
    except Exception:
        pass
    return 84.0


def _detect_inr_in_input(user_input: str) -> tuple:
    """
    Check if user mentioned budget in INR directly.
    Returns (amount_inr, found) — found=True means skip USD conversion.
    Handles: Rs, INR, ₹, rupees, rupee
    Examples: "Rs 20000", "₹45,000", "20000 rupees", "INR 50000"
    """
    text = user_input.lower().replace(",", "")
    patterns = [
        r'rs\.?\s*(\d+)',
        r'₹\s*(\d+)',
        r'inr\s*(\d+)',
        r'(\d+)\s*(?:rupees?|inr)',
        r'rupees?\s*(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            amount = float(m.group(1))
            print("INR budget detected in input: Rs " + str(int(amount)))
            return amount, True
    return 0.0, False


class ExtractionAgent(BaseAgent):
    """Parse user free-text into travel_details.
    Extracts start_date, computes end_date.
    Budget is kept in INR if user specified INR — no double conversion."""

    def extract_details(self, user_input: str) -> dict:
        today_str = date.today().isoformat()

        # ── Detect INR budget BEFORE calling LLM ──────────────────────────────
        # This prevents the LLM from misinterpreting Rs as USD
        inr_from_input, user_gave_inr = _detect_inr_in_input(user_input)

        system_prompt = (
            "You are a travel data extraction expert. "
            "Extract travel info and return ONLY valid JSON, nothing else. "
            "Today's date is " + today_str + ". "
            "When the user mentions a start date parse it carefully. "
            "If no start date is mentioned use today's date."
        )

        user_prompt = (
            "Extract from the user request below.\n\n"
            "User Request: \"" + user_input + "\"\n\n"
            "Today is: " + today_str + "\n\n"
            "Return a JSON object with exactly these keys:\n"
            "  destination   - city and country string\n"
            "  duration      - number of days as integer (default 5)\n"
            "  start_date    - trip start date as YYYY-MM-DD "
            "(parse from user input; if not mentioned use " + today_str + ")\n"
            "  budget_raw    - the budget NUMBER exactly as the user stated it "
            "(e.g. if user says Rs 20000 write 20000, if user says $500 write 500, "
            "if user says 45000 rupees write 45000). Do NOT convert currencies.\n"
            "  budget_currency - 'INR' if user mentioned Rs/rupees/INR/₹, "
            "else 'USD' if user mentioned $/dollars, else 'INR' as default for Indian trips\n"
            "  travel_type   - Adventure/Cultural/Relaxation/Family/Romantic/Business/Solo\n"
            "  travelers     - number of people as integer (default 2)\n"
            "  interests     - array of interest strings\n"
            "  overview      - 2-3 sentence destination overview\n\n"
            "IMPORTANT for start_date:\n"
            "- '1st April' or 'April 1' → use current or next April 1\n"
            "- 'next week' → add 7 days to today\n"
            "- 'tomorrow'  → add 1 day to today\n"
            "Return ONLY the JSON object, no other text."
        )

        response = self.clean_json(self.invoke(system_prompt, user_prompt))
        print(response)

        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            print("JSON decode error (extraction): " + str(e))
            data = {
                "destination": "unknown", "duration": 5,
                "start_date": today_str, "budget_raw": 20000,
                "budget_currency": "INR", "travel_type": "General",
                "travelers": 2, "interests": ["sightseeing"],
                "overview": "Exciting destination to explore"
            }

        # ── Validate start_date ────────────────────────────────────────────────
        raw_start = str(data.get("start_date", today_str) or today_str).strip()
        try:
            start = date.fromisoformat(raw_start)
        except ValueError:
            print("Could not parse start_date '" + raw_start + "', defaulting to today")
            start = date.today()

        duration = int(data.get("duration", 5))
        end      = start + timedelta(days=duration - 1)

        data["start_date"]      = start.isoformat()
        data["end_date"]        = end.isoformat()
        data["duration"]        = duration
        data["days_until_trip"] = (start - date.today()).days

        m = start.month
        if m in (12, 1, 2):   data["season"] = "Winter"
        elif m in (3, 4, 5):  data["season"] = "Spring/Summer"
        elif m in (6, 7, 8, 9): data["season"] = "Monsoon/Summer"
        else:                  data["season"] = "Autumn/Post-monsoon"

        # ── Budget: convert correctly based on currency ────────────────────────
        inr_rate = _live_inr_rate()

        # Priority 1: regex detected INR in user input (most reliable)
        if user_gave_inr:
            budget_inr = inr_from_input
            budget_usd = round(budget_inr / inr_rate, 2)
            print("Using regex-detected INR budget: Rs " + str(int(budget_inr)))

        else:
            # Priority 2: use what the LLM extracted + its currency label
            budget_raw      = float(data.get("budget_raw", 0) or 0)
            budget_currency = str(data.get("budget_currency", "INR")).upper().strip()

            if budget_raw <= 0:
                # Fallback: check old budget_usd key if LLM used old format
                budget_raw = float(data.get("budget_usd", 20000) or 20000)
                budget_currency = "INR"  # safer default for Indian users

            if budget_currency == "USD":
                budget_usd = budget_raw
                budget_inr = round(budget_raw * inr_rate, 2)
                print("USD budget: $" + str(budget_usd) + " = Rs " + str(budget_inr))
            else:
                # INR — use directly, no multiplication
                budget_inr = budget_raw
                budget_usd = round(budget_raw / inr_rate, 2)
                print("INR budget: Rs " + str(int(budget_inr)))

        data["budget_inr"] = round(budget_inr, 2)
        data["budget_usd"] = budget_usd
        data["inr_rate"]   = inr_rate
        data["budget"]     = budget_usd   # backward compat

        print("Final budget: Rs " + str(data["budget_inr"]) +
              " ($" + str(data["budget_usd"]) + ")" +
              " | Rate: " + str(inr_rate) +
              " | Trip: " + data["destination"] +
              " " + data["start_date"] + " to " + data["end_date"])
        return data
