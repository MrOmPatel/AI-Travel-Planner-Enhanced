import json
import hashlib
from apscheduler.schedulers.background import BackgroundScheduler
from agents.weather_agent import WeatherAgent
from agents.itinerary_agent import ItineraryAgent
from database import get_all_trips, update_last_checked
from email_service import send_alert

weather_agent   = WeatherAgent()
itinerary_agent = ItineraryAgent()
TEMP_DELTA = 5
BAD_CONDS  = ("Rainy", "Thunderstorm", "Extreme Heat", "Snow", "Drizzle")

def _event_hash(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]

def _weather_body(destination, old_temp, old_cond, new_temp, new_cond, advice, forecast_days):
    rows = ""
    for d in forecast_days[:5]:
        bg   = "#f0fdf4" if d.get("is_outdoor_ok") else "#fef9c3"
        rows += ("<tr style=background:" + bg + ">"
                 "<td style=padding:6px>" + d["date"] + "</td>"
                 "<td>" + d["condition"] + "</td>"
                 "<td>" + str(d["temp_c"]) + "C</td></tr>")
    old_lbl = str(old_cond) + " " + str(old_temp) + "C" if old_temp else "Unknown"
    new_lbl = str(new_cond) + " " + str(new_temp) + "C"
    table   = ("<table style=border-collapse:collapse;width:100%;margin:12px_0>"
               "<tr style=background:#fee2e2><td style=padding:8px>Was</td><td>" + old_lbl + "</td></tr>"
               "<tr style=background:#dcfce7><td style=padding:8px>Now</td><td><b>" + new_lbl + "</b></td></tr>"
               "</table>")
    adv = "<p style=background:#eff6ff;padding:12px;border-radius:6px>" + advice + "</p>"
    fc  = ""
    if rows:
        fc = "<table style=border-collapse:collapse;width:100%><tr style=background:#f3f4f6><th>Date</th><th>Condition</th><th>Temp</th></tr>" + rows + "</table>"
    return ("<p>Weather at <b>" + destination + "</b> changed since you saved this trip.</p>"
            + table + adv + fc)

def _events_body(destination, events_text):
    lines = [l.strip() for l in events_text.split("||") if l.strip()]
    items = "".join("<li style=margin:6px_0>" + l.lstrip("- ") + "</li>" for l in lines)
    return ("<p>New events detected at <b>" + destination + "</b>:</p>"
            "<ul style=background:#f5f3ff;padding:16px;border-left:4px_solid_#7c3aed>" + items + "</ul>"
            "<p>Consider updating your itinerary!</p>")

def check_trip(trip):
    trip_id = trip["id"]
    email   = trip["email"]
    dest    = trip["destination"]
    dur     = trip["duration"]
    baseline = json.loads(trip.get("baseline_weather") or "{}")
    old_hash = trip.get("last_event_hash") or ""
    new_hash = old_hash
    try:
        cur = weather_agent.get_weather(dest, dur)
        if cur.get("data_available"):
            ot = baseline.get("current_temp_c")
            nt = cur.get("current_temp_c")
            oc = baseline.get("condition", "")
            nc = cur.get("condition", "")
            temp_chg = ot is not None and nt is not None and abs(nt - ot) >= TEMP_DELTA
            cond_bad = nc in BAD_CONDS and oc not in BAD_CONDS and oc != nc
            if temp_chg or cond_bad:
                body = _weather_body(dest, ot, oc, nt, nc, cur.get("advice",""), cur.get("daily_forecast",[]))
                send_alert(email, dest, "Weather Changed: " + nc + " (" + str(nt) + "C)", body)
    except Exception as e:
        print("Weather check error trip " + str(trip_id) + ": " + str(e))
    try:
        ev = itinerary_agent._fetch_events(dest)
        if ev and ev != "No event data":
            nh = _event_hash(ev)
            if nh != old_hash:
                items = "".join("<li style=margin:6px_0>" + l.strip().lstrip("- ") + "</li>"
                                 for l in ev.split("\n") if l.strip())
                body  = ("<p>New events at <b>" + dest + "</b>:</p>"
                         "<ul style=background:#f5f3ff;padding:16px;border-left:4px solid #7c3aed>" + items + "</ul>")
                send_alert(email, dest, "New Events Detected at " + dest, body)
                new_hash = nh
    except Exception as e:
        print("Event check error trip " + str(trip_id) + ": " + str(e))
    update_last_checked(trip_id, new_hash)

def check_all_trips():
    print("Running scheduled trip checks...")
    trips = get_all_trips()
    if not trips:
        print("No saved trips.")
        return
    print("Checking " + str(len(trips)) + " trip(s)...")
    for t in trips:
        check_trip(t)
    print("Check complete.")

def start_scheduler():
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        check_all_trips,
        trigger="interval",
        hours=6,
        id="trip_alert_checker",
        max_instances=1,
        misfire_grace_time=300
    )
    scheduler.start()
    print("Scheduler started — checks every 6 hours.")
    return scheduler