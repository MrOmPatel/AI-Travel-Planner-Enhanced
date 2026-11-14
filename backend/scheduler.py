import hashlib
import html
import json
import re
from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler
from agents.weather_agent import WeatherAgent
from agents.itinerary_agent import ItineraryAgent
from database import get_all_trips, update_monitoring_state
from email_service import send_alert

weather_agent = WeatherAgent()
itinerary_agent = ItineraryAgent()
TEMP_DELTA = 5
BAD_CONDS = {"Rainy", "Thunderstorm", "Extreme Heat", "Snow", "Drizzle"}
_scheduler = None


def _normalise_event_text(text):
    lines = []
    for line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", line.strip().lstrip("-*• ")).strip().lower()
        # Search snippets fluctuate frequently; compare event titles, not snippets.
        title = line.split(":", 1)[0].strip()
        if title and title != "no event data":
            lines.append(title)
    return "\n".join(sorted(set(lines)))


def _event_hash(text):
    normalized = _normalise_event_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _live_forecast_map(weather):
    if not weather or weather.get("forecast_type") != "live":
        return {}
    result = {}
    for item in weather.get("daily_forecast", []):
        if item.get("source", "live") != "live" or not item.get("date"):
            continue
        result[item["date"]] = {
            "condition": str(item.get("condition", "Unknown")),
            "temp_c": item.get("temp_c"),
        }
    return result


def _weather_changes(previous, current):
    """Return material forecast changes by trip date; ignore seasonal estimates."""
    old_map = _live_forecast_map(previous)
    new_map = _live_forecast_map(current)
    if not old_map or not new_map:
        return []
    changes = []
    for day, new in sorted(new_map.items()):
        old = old_map.get(day)
        if not old:
            continue
        old_temp, new_temp = old.get("temp_c"), new.get("temp_c")
        temp_changed = (isinstance(old_temp, (int, float)) and
                        isinstance(new_temp, (int, float)) and
                        abs(float(new_temp) - float(old_temp)) >= TEMP_DELTA)
        condition_changed = (new.get("condition") in BAD_CONDS and
                             old.get("condition") not in BAD_CONDS)
        if temp_changed or condition_changed:
            changes.append({"date": day, "before": old, "after": new,
                            "temperature_changed": temp_changed,
                            "condition_changed": condition_changed})
    return changes


def _weather_body(destination, changes, advice, forecast_days):
    rows = []
    for change in changes:
        before, after = change["before"], change["after"]
        rows.append(
            "<tr><td style='padding:7px'>" + html.escape(change["date"]) + "</td>"
            "<td style='padding:7px'>" + html.escape(str(before.get("condition"))) +
            " / " + html.escape(str(before.get("temp_c"))) + "°C</td>"
            "<td style='padding:7px'><b>" + html.escape(str(after.get("condition"))) +
            " / " + html.escape(str(after.get("temp_c"))) + "°C</b></td></tr>"
        )
    forecast_rows = []
    for day in forecast_days[:5]:
        forecast_rows.append(
            "<tr><td style='padding:6px'>" + html.escape(str(day.get("date", ""))) + "</td>"
            "<td style='padding:6px'>" + html.escape(str(day.get("condition", ""))) + "</td>"
            "<td style='padding:6px'>" + html.escape(str(day.get("temp_c", ""))) + "°C</td></tr>"
        )
    table = ("<table style='border-collapse:collapse;width:100%'>"
             "<tr><th>Date</th><th>Previous forecast</th><th>Updated forecast</th></tr>" +
             "".join(rows) + "</table>")
    forecast = ("<h3>Current trip forecast</h3><table>" + "".join(forecast_rows) +
                "</table>") if forecast_rows else ""
    return ("<p>Material weather changes were detected for <b>" +
            html.escape(destination) + "</b>.</p>" + table +
            "<p>" + html.escape(advice or "Please review your plans.") + "</p>" + forecast)


def _events_body(destination, events_text):
    lines = [html.escape(line.strip().lstrip("-*• "))
             for line in (events_text or "").splitlines() if line.strip()]
    items = "".join("<li style='margin:6px 0'>" + line + "</li>" for line in lines)
    return ("<p>New or changed event information was detected at <b>" +
            html.escape(destination) + "</b>:</p><ul>" + items + "</ul>")


def _load_json(value):
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}


def check_trip(trip):
    trip_id = trip["id"]
    email = trip["email"]
    destination = trip["destination"]
    duration = int(trip.get("duration") or 1)
    start_date = trip.get("start_date") or date.today().isoformat()
    end_date = trip.get("end_date") or ""

    if end_date and end_date < date.today().isoformat():
        print("Skipping expired trip " + str(trip_id))
        return

    weather_enabled = bool(trip.get("weather_alerts", 1))
    events_enabled = bool(trip.get("event_alerts", 1))
    baseline = _load_json(trip.get("baseline_weather"))
    previous_weather = _load_json(trip.get("last_weather_snapshot")) or baseline
    pending_weather_snapshot = None
    pending_event_hash = None

    if weather_enabled:
        try:
            current = weather_agent.get_weather(destination, duration, start_date)
            # Seasonal estimates are not observations and must never trigger alerts.
            if current.get("forecast_type") == "live":
                previous_is_live = previous_weather.get("forecast_type") == "live"
                if previous_is_live:
                    changes = _weather_changes(previous_weather, current)
                    if changes:
                        sent = send_alert(
                            email, destination, "Weather forecast changed",
                            _weather_body(destination, changes, current.get("advice", ""),
                                          current.get("daily_forecast", []))
                        )
                        if sent:
                            pending_weather_snapshot = current
                        else:
                            print("Weather alert delivery failed; will retry on next check")
                    else:
                        pending_weather_snapshot = current
                else:
                    # First live response becomes the baseline without a false alert.
                    pending_weather_snapshot = current
        except Exception as exc:
            print("Weather check error trip " + str(trip_id) + ": " + str(exc))

    if events_enabled:
        try:
            events = itinerary_agent._fetch_events(destination, start_date, end_date or None)
            current_hash = _event_hash(events)
            previous_hash = trip.get("last_event_hash") or ""
            if current_hash:
                if previous_hash and current_hash != previous_hash:
                    sent = send_alert(
                        email, destination, "New event information detected",
                        _events_body(destination, events)
                    )
                    if sent:
                        pending_event_hash = current_hash
                    else:
                        print("Event alert delivery failed; will retry on next check")
                else:
                    # First successful lookup establishes baseline; no false first alert.
                    pending_event_hash = current_hash
        except Exception as exc:
            print("Event check error trip " + str(trip_id) + ": " + str(exc))

    # Record the check even when no provider returned data or no alert was needed.
    update_monitoring_state(
        trip_id,
        last_event_hash=pending_event_hash,
        last_weather_snapshot=pending_weather_snapshot,
    )


def check_all_trips():
    print("Running scheduled trip checks...")
    trips = get_all_trips()
    if not trips:
        print("No saved trips.")
        return
    print("Checking " + str(len(trips)) + " trip(s)...")
    for trip in trips:
        check_trip(trip)
    print("Check complete.")


def start_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler
    _scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
    _scheduler.add_job(
        check_all_trips, trigger="interval", hours=6,
        id="trip_alert_checker", max_instances=1,
        coalesce=True, misfire_grace_time=300, replace_existing=True,
    )
    _scheduler.start()
    print("Scheduler started — checks every 6 hours.")
    return _scheduler
