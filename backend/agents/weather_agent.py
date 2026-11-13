import os
import requests
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

OWM_BASE = "https://api.openweathermap.org/data/2.5"
OWM_FORECAST_DAYS = 5   # free tier limit

# Condition labels and scheduling advice
WEATHER_ADVICE = {
    "clear":        ("Sunny",        "Great for all outdoor attractions!"),
    "clouds":       ("Cloudy",       "Good for outdoor sightseeing."),
    "rain":         ("Rainy",        "Move outdoor spots to morning. Prioritise indoor museums in afternoon."),
    "drizzle":      ("Drizzle",      "Carry an umbrella. Outdoor visits ok in the morning."),
    "thunderstorm": ("Thunderstorm", "Avoid outdoor sites. Visit indoor museums, malls, restaurants."),
    "snow":         ("Snow",         "Dress warm. Check if attractions are open before visiting."),
    "mist":         ("Misty",        "Low visibility. Indoor venues or midday outdoor visits preferred."),
    "haze":         ("Hazy",         "Limit outdoor time in afternoon. Indoor venues better."),
    "extreme_heat": ("Extreme Heat", "Go outdoors before 11 AM and after 5 PM. Indoors at midday."),
    "unknown":      ("Unknown",      "Weather data unavailable. Plan as usual."),
}

# Seasonal typical weather per month — used when trip is beyond 5-day forecast
SEASONAL_PROFILE = {
    1:  {"condition": "clear",  "temp_c": 15, "advice": "Winter — cool and clear. Perfect for outdoor sightseeing."},
    2:  {"condition": "clear",  "temp_c": 18, "advice": "Late winter — mild and pleasant. Great for outdoor trips."},
    3:  {"condition": "clear",  "temp_c": 24, "advice": "Spring — warm and sunny. Ideal for outdoor activities."},
    4:  {"condition": "clear",  "temp_c": 30, "advice": "Spring/Summer — warm days. Plan outdoor visits before noon."},
    5:  {"condition": "extreme_heat", "temp_c": 36, "advice": "Hot summer — avoid outdoors 11 AM–5 PM. Early morning visits best."},
    6:  {"condition": "rain",   "temp_c": 32, "advice": "Pre-monsoon / early monsoon — carry umbrella, some rain expected."},
    7:  {"condition": "rain",   "temp_c": 28, "advice": "Monsoon — frequent rain. Indoor venues and covered attractions preferred."},
    8:  {"condition": "rain",   "temp_c": 28, "advice": "Monsoon — pack rain gear. Schedule outdoor visits for morning gaps."},
    9:  {"condition": "clouds", "temp_c": 28, "advice": "Post-monsoon — occasional showers but clearing up. Mix of indoor/outdoor fine."},
    10: {"condition": "clear",  "temp_c": 26, "advice": "Autumn — pleasant weather. Excellent time for all outdoor activities."},
    11: {"condition": "clear",  "temp_c": 22, "advice": "Early winter — cool and clear. Great for sightseeing."},
    12: {"condition": "clear",  "temp_c": 17, "advice": "Winter — cool days and cold nights. Outdoor activities best midday."},
}


class WeatherAgent:
    """Fetch weather for the trip's actual start date.

    - Trip starts within 5 days  → live OWM forecast filtered to start date
    - Trip starts 6–16 days away → OWM 16-day daily forecast (paid) not available
                                   on free tier, so use seasonal fallback
    - Trip starts 17+ days away  → seasonal fallback only
    - No API key                 → seasonal fallback always
    """

    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY", "")

    def _classify(self, weather_id: int, temp_c: float) -> str:
        if temp_c >= 40:            return "extreme_heat"
        if 200 <= weather_id < 300: return "thunderstorm"
        if 300 <= weather_id < 400: return "drizzle"
        if 500 <= weather_id < 600: return "rain"
        if 600 <= weather_id < 700: return "snow"
        if weather_id in (701, 721, 741): return "mist"
        if weather_id in (711, 731, 751, 761, 762): return "haze"
        if weather_id == 800:       return "clear"
        if 801 <= weather_id <= 804: return "clouds"
        return "unknown"

    def get_weather(self, destination: str, duration: int,
                    start_date: str = None) -> dict:
        """
        start_date: ISO string 'YYYY-MM-DD'. If None, defaults to today.
        """
        today      = date.today()
        trip_start = date.fromisoformat(start_date) if start_date else today
        days_away  = (trip_start - today).days

        print("Weather request: " + destination +
              " | start: " + str(trip_start) +
              " | " + str(days_away) + " days away")

        # ── Case 1: no API key — always seasonal ─────────────────────────────
        if not self.api_key:
            print("No OPENWEATHER_API_KEY — using seasonal estimate")
            return self._seasonal(destination, trip_start, duration)

        # ── Case 2: trip starts within 5 days — use live OWM forecast ─────────
        if days_away <= OWM_FORECAST_DAYS:
            return self._live_forecast(destination, duration, trip_start, days_away)

        # ── Case 3: trip is far future — seasonal fallback with explanation ───
        print("Trip is " + str(days_away) + " days away — beyond live forecast, using seasonal estimate")
        return self._seasonal(destination, trip_start, duration)

    # ── Live forecast (trip within 5 days) ────────────────────────────────────
    def _live_forecast(self, destination: str, duration: int,
                       trip_start: date, days_away: int) -> dict:
        try:
            # Current conditions
            cr = requests.get(OWM_BASE + "/weather", params={
                "q": destination, "appid": self.api_key, "units": "metric"
            }, timeout=8)
            if cr.status_code != 200:
                return self._seasonal(destination, trip_start, duration)

            cur       = cr.json()
            temp_c    = cur["main"]["temp"]
            feels     = cur["main"]["feels_like"]
            humidity  = cur["main"]["humidity"]
            wid       = cur["weather"][0]["id"]
            desc      = cur["weather"][0]["description"].title()
            city_name = cur.get("name", destination)
            key       = self._classify(wid, temp_c)
            label, advice = WEATHER_ADVICE[key]

            # 5-day 3-hour forecast
            fr = requests.get(OWM_BASE + "/forecast", params={
                "q": destination, "appid": self.api_key,
                "units": "metric", "cnt": 40
            }, timeout=8)

            daily = []
            if fr.status_code == 200:
                # Group entries by date, prefer noon slot
                seen = {}
                for item in fr.json().get("list", []):
                    d    = item["dt_txt"][:10]
                    hour = int(item["dt_txt"][11:13])
                    prev = int(seen[d]["dt_txt"][11:13]) if d in seen else 99
                    if d not in seen or abs(hour - 12) < abs(prev - 12):
                        seen[d] = item

                # Build list starting from trip_start date
                trip_start_str = trip_start.isoformat()
                all_dates = sorted(seen.keys())

                # Find dates from trip_start onward
                trip_dates = [d for d in all_dates if d >= trip_start_str]

                # If no forecast data for trip_start (e.g. today IS start), use all from today
                if not trip_dates:
                    trip_dates = all_dates

                for d in trip_dates[:duration]:
                    item   = seen[d]
                    fwid   = item["weather"][0]["id"]
                    ftemp  = item["main"]["temp"]
                    fkey   = self._classify(fwid, ftemp)
                    flabel, fadvice = WEATHER_ADVICE[fkey]
                    daily.append({
                        "date":          d,
                        "condition":     flabel,
                        "temp_c":        round(ftemp, 1),
                        "description":   item["weather"][0]["description"].title(),
                        "advice":        fadvice,
                        "is_outdoor_ok": fkey in ("clear", "clouds"),
                        "source":        "live",
                    })

            # If fewer live days than duration, fill remaining with seasonal
            existing_dates = {d["date"] for d in daily}
            for i in range(duration):
                d_obj = trip_start + timedelta(days=i)
                d_str = d_obj.isoformat()
                if d_str not in existing_dates:
                    season_day = self._seasonal_day(d_obj)
                    season_day["date"]   = d_str
                    season_day["source"] = "seasonal_estimate"
                    daily.append(season_day)

            daily.sort(key=lambda x: x["date"])
            daily = daily[:duration]

            is_start_day = days_away <= 0
            current_label = label if is_start_day else (daily[0]["condition"] if daily else label)
            current_temp  = temp_c if is_start_day else (daily[0]["temp_c"]    if daily else temp_c)

            print("Live weather: " + city_name + " | " + label + " " + str(round(temp_c, 1)) + "C")
            return {
                "city":             city_name,
                "current_temp_c":   round(current_temp, 1),
                "feels_like_c":     round(feels, 1) if is_start_day else None,
                "humidity_pct":     humidity if is_start_day else None,
                "condition":        current_label,
                "description":      desc if is_start_day else "Forecast for trip dates",
                "advice":           advice,
                "is_outdoor_ok":    key in ("clear", "clouds"),
                "daily_forecast":   daily,
                "data_available":   True,
                "forecast_type":    "live",
                "trip_start_date":  trip_start.isoformat(),
                "days_until_trip":  days_away,
            }
        except Exception as e:
            print("Live weather error: " + str(e))
            return self._seasonal(destination, trip_start, duration)

    # ── Seasonal fallback (trip is far future) ────────────────────────────────
    def _seasonal(self, destination: str, trip_start: date, duration: int) -> dict:
        profile     = SEASONAL_PROFILE[trip_start.month]
        key         = profile["condition"]
        label, _    = WEATHER_ADVICE[key]
        advice      = profile["advice"]
        temp_c      = profile["temp_c"]
        days_away   = (trip_start - date.today()).days

        daily = []
        for i in range(duration):
            d_obj   = trip_start + timedelta(days=i)
            day_data = self._seasonal_day(d_obj)
            daily.append(day_data)

        print("Seasonal forecast for " + destination + " in " +
              trip_start.strftime("%B") + ": " + label + " ~" + str(temp_c) + "C")

        note = (
            "Trip is " + str(days_away) + " days away. "
            "Showing seasonal estimate for " + trip_start.strftime("%B %Y") + ". "
            "Live forecast will be available closer to your trip date."
            if days_away > 0 else
            "Seasonal estimate — add OPENWEATHER_API_KEY to .env for live data."
        )

        return {
            "city":             destination,
            "current_temp_c":   temp_c,
            "feels_like_c":     None,
            "humidity_pct":     None,
            "condition":        label,
            "description":      "Seasonal estimate for " + trip_start.strftime("%B"),
            "advice":           advice,
            "is_outdoor_ok":    key in ("clear", "clouds"),
            "daily_forecast":   daily,
            "data_available":   True,
            "forecast_type":    "seasonal",
            "trip_start_date":  trip_start.isoformat(),
            "days_until_trip":  days_away,
            "seasonal_note":    note,
        }

    def _seasonal_day(self, d: date) -> dict:
        profile     = SEASONAL_PROFILE[d.month]
        key         = profile["condition"]
        label, adv  = WEATHER_ADVICE[key]
        return {
            "date":          d.isoformat(),
            "condition":     label,
            "temp_c":        profile["temp_c"],
            "description":   "Seasonal estimate",
            "advice":        adv,
            "is_outdoor_ok": key in ("clear", "clouds"),
            "source":        "seasonal_estimate",
        }

    def _fallback(self, destination: str) -> dict:
        return {
            "city": destination, "current_temp_c": None, "feels_like_c": None,
            "humidity_pct": None, "condition": "Unknown", "description": "Unavailable",
            "advice": WEATHER_ADVICE["unknown"][1], "is_outdoor_ok": True,
            "daily_forecast": [], "data_available": False, "forecast_type": "none",
        }
