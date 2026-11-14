import os
import re
import json
import time
import hashlib
import requests
from difflib import SequenceMatcher
from pathlib import Path
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

    def geocode_place(self, place_name: str, locality: str = "", destination: str = "",
                      evidence=None) -> tuple:
        """Resolve a named POI with Nominatim; return (lat, lon) or None.

        Search terms are generated from the supplied place and live Tavily evidence;
        there is deliberately no manually maintained alias list. Results are cached
        only after name/locality validation. Public Nominatim is throttled to 1 req/sec.
        """
        name = str(place_name or "").strip()
        if not name:
            return None
        locality = str(locality or "").strip()
        destination = str(destination or "").strip()
        cache_path = Path(__file__).resolve().parent / ".geocode_cache.json"
        try:
            cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        except Exception:
            cache = {}
        cache_key = hashlib.sha256("|".join((name.lower(), locality.lower(), destination.lower())).encode()).hexdigest()
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and cached.get("verified"):
            return float(cached["lat"]), float(cached["lon"])

        # Tavily titles/snippets can expose a canonical name used by geographic data.
        # These are runtime candidates, not a hand-maintained alias dictionary.
        search_terms = [name]
        for item in (evidence or []):
            title = str(item.get("title", "")).strip() if isinstance(item, dict) else ""
            content = str(item.get("content", "")) if isinstance(item, dict) else ""
            if title and len(title) <= 110:
                search_terms.append(title)
            # Extract quoted/heading-like proper-name phrases from relevant snippets.
            for phrase in re.findall(r"(?:^|[.!?])\s*([A-Z][A-Za-z0-9&'’ -]{3,65})", content):
                phrase = phrase.strip(" -,:;")
                if phrase and len(phrase.split()) <= 8:
                    search_terms.append(phrase)
        unique_terms = []
        seen = set()
        for term in search_terms:
            key = re.sub(r"\W+", " ", term.lower()).strip()
            if key and key not in seen:
                seen.add(key); unique_terms.append(term)
        locality_tokens = {t for t in re.findall(r"[a-z0-9]+", locality.lower()) if len(t) > 2}
        destination_tokens = {t for t in re.findall(r"[a-z0-9]+", destination.lower()) if len(t) > 2}
        name_tokens = {t for t in re.findall(r"[a-z0-9]+", name.lower()) if len(t) > 2}

        # Keep the public Nominatim endpoint below its one-request-per-second policy.
        for term in unique_terms[:3]:
            query = ", ".join(x for x in (term, locality, destination) if x)
            try:
                time.sleep(1.1)
                response = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": query, "format": "jsonv2", "addressdetails": 1,
                            "namedetails": 1, "extratags": 1, "limit": 5},
                    headers={"User-Agent": "AITripPlanner/1.0 (travel itinerary geocoding)"},
                    timeout=10
                )
                if response.status_code == 429:
                    print("Nominatim rate limit reached; skipping geocode for " + name)
                    return None
                response.raise_for_status()
                candidates = response.json()
            except Exception as exc:
                print("Nominatim lookup failed for " + name + ": " + str(exc))
                candidates = []
            for candidate in candidates:
                display = str(candidate.get("display_name", ""))
                namedetails = candidate.get("namedetails") or {}
                candidate_names = [candidate.get("name", "")] + [
                    v for k, v in namedetails.items() if k in ("name", "name:en", "official_name", "short_name", "alt_name")
                ]
                candidate_names = [str(v) for v in candidate_names if v]
                best = max((SequenceMatcher(None, name.lower(), v.lower()).ratio() for v in candidate_names), default=0.0)
                token_match = len(name_tokens.intersection(set(re.findall(r"[a-z0-9]+", (" ".join(candidate_names)).lower())))) / max(1, len(name_tokens))
                # If Tavily supplied a canonical title, compare that query term too.
                term_score = max((SequenceMatcher(None, term.lower(), v.lower()).ratio() for v in candidate_names), default=0.0)
                score = max(best, 0.65 * token_match + 0.35 * term_score)
                address = candidate.get("address") or {}
                address_text = " ".join(str(v) for v in address.values()).lower() + " " + display.lower()
                locality_match = (any(t in address_text for t in locality_tokens)
                                  if locality_tokens else
                                  (not destination_tokens or any(t in address_text for t in destination_tokens)))
                if score < 0.48 or not locality_match:
                    continue
                try:
                    lat, lon = float(candidate["lat"]), float(candidate["lon"])
                except (KeyError, TypeError, ValueError):
                    continue
                if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
                    continue
                # Reject broad administrative areas when the requested attraction is a POI.
                category = str(candidate.get("category", "")).lower()
                ctype = str(candidate.get("type", "")).lower()
                if category in ("boundary", "place") and ctype in ("administrative", "city", "town", "village", "county", "state") and score < 0.85:
                    continue
                cache[cache_key] = {"lat": lat, "lon": lon, "verified": True,
                                    "display_name": display, "matched_name": candidate_names[0] if candidate_names else term}
                try:
                    cache_path.write_text(json.dumps(cache, indent=2))
                except Exception:
                    pass
                print(f"[GEOCODE VERIFIED] {name} -> {lat}, {lon} ({display[:90]})")
                return lat, lon
            time.sleep(1.1)
        print("[GEOCODE UNVERIFIED] " + name + " — no sufficiently reliable Nominatim match")
        return None

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
