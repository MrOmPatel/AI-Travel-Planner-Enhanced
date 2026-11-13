import os
import requests
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

EXCHANGE_URL = "https://open.er-api.com/v6/latest/USD"


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — Wikipedia (best for named places / attractions)
# Free, no API key, returns the real photo of the actual place
# ─────────────────────────────────────────────────────────────────────────────

def _wikipedia_image(place_name: str) -> str:
    """
    Fetch the thumbnail image for a named place from Wikipedia.
    Returns the image URL string, or "" if not found.
    Works best for well-known attractions: temples, forts, palaces, landmarks.
    """
    if not place_name:
        return ""
    # Wikipedia REST API — page summary endpoint returns thumbnail
    # Replace spaces with underscores for the page title format
    title = place_name.strip().replace(" ", "_")
    try:
        r = requests.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(title),
            headers={"User-Agent": "AITripPlanner/1.0"},
            timeout=6
        )
        if r.status_code == 200:
            data = r.json()
            # thumbnail.source is the actual place photo used on Wikipedia
            img = data.get("thumbnail", {}).get("source", "")
            if img:
                # Upgrade resolution: replace /320px- with /800px-
                img = img.replace("/320px-", "/800px-").replace("/200px-", "/800px-")
                print("Wikipedia image: " + place_name[:40] + " → " + img[:60])
                return img
    except Exception as e:
        print("Wikipedia image failed (" + place_name[:30] + "): " + str(e))
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# TIER 2 — Pexels API (best for hotels, restaurants, food, generic travel)
# Free tier: 200 requests/hour — requires PEXELS_API_KEY in .env
# ─────────────────────────────────────────────────────────────────────────────

def _pexels_image(query: str) -> str:
    """
    Search Pexels for a landscape photo matching the query.
    Returns image URL string, or "" if no key or no results.
    """
    api_key = os.getenv("PEXELS_API_KEY", "").strip()
    if not api_key:
        return ""
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            timeout=8
        )
        if r.status_code == 200:
            photos = r.json().get("photos", [])
            if photos:
                url = photos[0].get("src", {}).get("large", "")
                if url:
                    print("Pexels image: " + query[:40])
                    return url
    except Exception as e:
        print("Pexels error (" + query[:30] + "): " + str(e))
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# TIER 3 — Picsum Photos (always works, free, no key, seed-based consistency)
# ─────────────────────────────────────────────────────────────────────────────

def _picsum_url(seed: str, w: int = 800, h: int = 600) -> str:
    """
    Picsum Photos — free, no API key, stable CDN.
    Seed-based: same query → same image every time.
    """
    clean = seed.lower().replace(" ", "-").replace(",", "").replace("'", "")[:40]
    return "https://picsum.photos/seed/" + clean + "/" + str(w) + "/" + str(h)


# ─────────────────────────────────────────────────────────────────────────────
# Geocoding — OpenStreetMap Nominatim (free, no key)
# ─────────────────────────────────────────────────────────────────────────────

def geocode_city(destination: str) -> tuple:
    """
    Get (lat, lon) for a city using Nominatim. Returns (0.0, 0.0) on failure.
    """
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": destination, "format": "json", "limit": 1},
            headers={"User-Agent": "AITripPlanner/1.0"},
            timeout=6
        )
        if r.status_code == 200 and r.json():
            result = r.json()[0]
            lat = float(result["lat"])
            lon = float(result["lon"])
            print("Geocoded '" + destination + "': " + str(lat) + ", " + str(lon))
            return lat, lon
    except Exception as e:
        print("Geocoding failed (" + str(e) + ")")
    return 0.0, 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Helper class
# ─────────────────────────────────────────────────────────────────────────────

class Helper:
    """
    Three-tier image system:
      Tier 1 — Wikipedia API    : real photo of the named place (places only)
      Tier 2 — Pexels API       : stock photo matched to query (all types)
      Tier 3 — Picsum Photos    : seed-based consistent fallback (always works)

    Usage:
      For places/attractions  → search_images(query, place_name=name)
      For hotels/restaurants  → search_images(query)   (skips Wikipedia)
    """

    def search_images(self, query: str, num_results: int = 1,
                      place_name: str = "", use_wikipedia: bool = False) -> list:
        """
        Return [image_url] using the three-tier strategy.

        place_name : the exact place name to look up on Wikipedia
        use_wikipedia : True for attractions/places, False for hotels/restaurants
        """

        # ── Tier 1: Wikipedia — only for named places/attractions ────────────
        if use_wikipedia and place_name:
            wiki = _wikipedia_image(place_name)
            if wiki:
                return [wiki]

        # ── Tier 2: Pexels — good for hotels, restaurants, generic travel ────
        pexels = _pexels_image(query)
        if pexels:
            return [pexels]

        # ── Tier 3: Picsum — always available, consistent per query ──────────
        url = _picsum_url(query)
        print("Picsum fallback: " + query[:40])
        return [url]

    def get_maps_link(self, place_name: str, city: str = "") -> str:
        query = (place_name + " " + city).strip()
        return "https://www.google.com/maps/search/?api=1&query=" + quote(query)

    def get_usd_to_inr(self) -> float:
        """Fetch live USD to INR rate. Falls back to 84.0."""
        try:
            r = requests.get(EXCHANGE_URL, timeout=5)
            if r.status_code == 200:
                rate = r.json().get("rates", {}).get("INR", 84.0)
                return float(rate)
        except Exception as e:
            print("Currency fetch failed (" + str(e) + "), using 84.0")
        return 84.0
