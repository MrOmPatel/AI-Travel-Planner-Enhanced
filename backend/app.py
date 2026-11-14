from flask import Flask, request, jsonify
from flask_cors import CORS
from workflow import TravelPlanWorkflow
from database import init_db, save_trip, get_all_trips, get_trips_by_email, delete_trip, update_trip_alert_preferences, update_trip_full_plan, get_trip_by_id_for_user
from auth import init_users_db, signup, login, verify_token, logout
from scheduler import start_scheduler, check_all_trips
from email_service import send_test_email
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
# Include local development origins plus the deployed Vercel URL.
frontend_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
configured_frontend = os.getenv("FRONTEND_URL", "").strip()
if configured_frontend:
    frontend_origins.extend(
        origin.strip().rstrip("/")
        for origin in configured_frontend.split(",")
        if origin.strip()
    )
CORS(app, origins=frontend_origins, allow_headers=["Content-Type", "Accept", "Authorization"],
     methods=["GET", "POST", "DELETE", "OPTIONS"])

def _auth(req) -> dict | None:
    """Extract and verify Bearer token from Authorization header."""
    hdr = req.headers.get("Authorization", "")
    token = hdr.replace("Bearer ", "").strip()
    return verify_token(token) if token else None

# ── Startup ────────────────────────────────────────────────────────────────────
init_db()
init_users_db()
start_scheduler()
workflow = TravelPlanWorkflow()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# ════════════════════════════════════════════════════════════════════════════════
#  AUTH ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/api/auth/signup", methods=["OPTIONS", "POST"])
def auth_signup():
    if request.method == "OPTIONS": return "", 204
    try:
        b = request.get_json()
        email    = b.get("email", "").strip()
        name     = b.get("name", "").strip()
        password = b.get("password", "")
        if not email or "@" not in email:
            return jsonify({"error": "Valid email required"}), 400
        if not name:
            return jsonify({"error": "Name required"}), 400
        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400
        result = signup(email, name, password)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auth/login", methods=["OPTIONS", "POST"])
def auth_login():
    if request.method == "OPTIONS": return "", 204
    try:
        b = request.get_json()
        result = login(b.get("email", ""), b.get("password", ""))
        if "error" in result:
            return jsonify(result), 401
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auth/logout", methods=["OPTIONS", "POST"])
def auth_logout():
    if request.method == "OPTIONS": return "", 204
    try:
        hdr = request.headers.get("Authorization", "")
        logout(hdr.replace("Bearer ", "").strip())
        return jsonify({"message": "Logged out"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auth/me", methods=["OPTIONS", "GET"])
def auth_me():
    if request.method == "OPTIONS": return "", 204
    user = _auth(request)
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({"email": user["email"], "name": user["name"]}), 200


# ════════════════════════════════════════════════════════════════════════════════
#  TRAVEL PLANNING
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/api/plan_travel", methods=["OPTIONS", "POST"])
def plan_travel():
    if request.method == "OPTIONS": return "", 204
    user = _auth(request)
    if not user:
        return jsonify({"error": "Please sign in or create an account before generating an itinerary."}), 401
    try:
        data = request.get_json() or {}
        user_input = data.get("user_input", "").strip()
        if not user_input:
            return jsonify({"error": "user_input is required"}), 400
        result = workflow.plan_travel(user_input)
        if result.get("error"):
            return jsonify({"error": result["error"]}), 500
        td = result.get("travel_details", {})
        if not td.get("destination") or not result.get("itinerary"):
            return jsonify({"error": "The itinerary could not be generated. Please try again."}), 500
        trip_id = save_trip(
            user["email"], td.get("destination", ""), int(td.get("duration", len(result.get("itinerary", [])) or 1)),
            td, result.get("weather", {}), result,
            td.get("start_date", ""), td.get("end_date", ""), user["user_id"],
            False, False
        )
        result["saved_trip_id"] = trip_id
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reoptimize_day", methods=["OPTIONS", "POST"])
def reoptimize_day():
    if request.method == "OPTIONS": return "", 204
    user = _auth(request)
    if not user:
        return jsonify({"error": "Please sign in to re-optimize your itinerary."}), 401
    try:
        body = request.get_json() or {}
        day_number = int(body.get("day_number", 1))
        trip_id = body.get("trip_id")
        saved_trip = get_trip_by_id_for_user(int(trip_id), user["user_id"]) if trip_id else None
        if trip_id and not saved_trip:
            return jsonify({"error": "Saved trip not found for this account."}), 404
        canonical_plan = saved_trip.get("full_plan", {}) if saved_trip else body.get("full_plan", {})
        canonical_days = canonical_plan.get("itinerary", []) if isinstance(canonical_plan, dict) else []
        if canonical_days and not (1 <= day_number <= len(canonical_days)):
            return jsonify({"error": "Invalid day number."}), 400
        used_places = []
        for index, day in enumerate(canonical_days):
            if index == day_number - 1: continue
            for activity in day.get("activities", []):
                if not activity.get("is_meal"):
                    name = str(activity.get("activity", "")).strip()
                    if name: used_places.append(name)
        # Fall back only for a not-yet-persisted plan; normal generated plans
        # always have a saved_trip_id and use the canonical database itinerary.
        if not canonical_days:
            used_places = body.get("used_places", [])
        updated_day = workflow.reoptimize_day(
            day_number, body.get("removed_attraction", ""),
            body.get("travel_details", {}), body.get("places", []),
            body.get("restaurants", []), body.get("weather", {}),
            used_places=used_places
        )
        if trip_id and updated_day:
            canonical_days[day_number - 1] = updated_day
            canonical_plan["itinerary"] = canonical_days
            if not update_trip_full_plan(int(trip_id), user["user_id"], canonical_plan):
                return jsonify({"error": "Could not update saved itinerary."}), 500
        return jsonify({"day": updated_day}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/weather", methods=["OPTIONS", "GET"])
def get_weather():
    if request.method == "OPTIONS": return "", 204
    try:
        destination = request.args.get("destination", "")
        duration    = int(request.args.get("duration", 5))
        if not destination:
            return jsonify({"error": "destination param required"}), 400
        return jsonify(workflow.weather_agent.get_weather(destination, duration)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════════════════════
#  SAVED TRIPS  (requires auth)
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/api/save_trip", methods=["OPTIONS", "POST"])
def save_trip_route():
    if request.method == "OPTIONS": return "", 204
    try:
        user = _auth(request)
        if not user:
            return jsonify({"error": "Please sign in to save a trip or activate alerts."}), 401
        body = request.get_json() or {}

        email      = user["email"].strip()
        user_id    = user["user_id"]
        destination     = body.get("destination", "").strip()
        duration        = int(body.get("duration", 5))
        travel_details  = body.get("travel_details", {})
        baseline_weather= body.get("weather", {})
        full_plan       = body.get("full_plan", {})
        start_date      = body.get("start_date", "")   # "YYYY-MM-DD"
        end_date        = body.get("end_date", "")     # "YYYY-MM-DD"
        weather_alerts  = bool(body.get("weather_alerts", True))
        event_alerts    = bool(body.get("event_alerts", True))

        if not email or "@" not in email:
            return jsonify({"error": "Valid email required"}), 400
        if not destination:
            return jsonify({"error": "Destination required"}), 400

        requested_trip_id = body.get("trip_id")
        if requested_trip_id:
            trip_id = int(requested_trip_id)
            if not update_trip_alert_preferences(trip_id, user_id, weather_alerts, event_alerts, start_date, end_date):
                return jsonify({"error": "Trip not found for this account."}), 404
        else:
            trip_id = save_trip(
                email, destination, duration, travel_details, baseline_weather,
                full_plan, start_date, end_date, user_id, weather_alerts, event_alerts
            )

        email_sent = send_test_email(email, weather_alerts, event_alerts)
        enabled = []
        if weather_alerts: enabled.append("weather")
        if event_alerts: enabled.append("event")
        alert_text = (" Enabled " + " and ".join(enabled) + " alerts will be checked every 6 hours."
                      if enabled else " Automatic weather and event alerts are disabled.")
        email_text = (" A confirmation email was sent to " + email + "."
                      if email_sent else " The trip was saved, but the confirmation email could not be delivered. Check your email configuration.")
        return jsonify({
            "message": "Trip saved." + alert_text + email_text,
            "trip_id": trip_id,
            "email_sent": bool(email_sent),
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/my_trips", methods=["OPTIONS", "GET"])
def my_trips():
    """Return all trips for the logged-in user, with status (upcoming/past)."""
    if request.method == "OPTIONS": return "", 204
    user = _auth(request)
    if not user:
        return jsonify({"error": "Login required to view saved trips"}), 401
    try:
        trips = [t for t in get_trips_by_email(user["email"]) if t.get("user_id") == user["user_id"]]
        # Keep complete itineraries for past trips, while also preparing a compact
        # overview for the history cards.
        for trip in trips:
            if trip.get("status") == "past":
                plan = trip.get("full_plan", {})
                places = plan.get("places", []) if isinstance(plan, dict) else []
                trip["overview_data"] = {
                    "places_visited": [p.get("name") for p in places if isinstance(p, dict) and p.get("name")],
                    "total_days": trip.get("duration"),
                    "destination": trip.get("destination"),
                    "budget_inr": plan.get("travel_details", {}).get("budget_inr") if isinstance(plan, dict) else None,
                    "budget_breakdown": plan.get("budget_breakdown", {}) if isinstance(plan, dict) else {},
                    "highlights": [p.get("name") for p in places[:4] if isinstance(p, dict) and p.get("name")],
                    "hotel_stayed": (plan.get("hotels") or [{}])[0].get("name") if isinstance(plan, dict) and plan.get("hotels") else None,
                }
        return jsonify({"trips": trips}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trip/<int:trip_id>", methods=["OPTIONS", "GET"])
def get_single_trip(trip_id):
    """Return full or summary data for one trip (auth required, must be owner)."""
    if request.method == "OPTIONS": return "", 204
    user = _auth(request)
    if not user:
        return jsonify({"error": "Login required"}), 401
    try:
        trips = [t for t in get_trips_by_email(user["email"]) if t.get("user_id") == user["user_id"]]
        trip  = next((t for t in trips if t["id"] == trip_id), None)
        if not trip:
            return jsonify({"error": "Trip not found"}), 404
        return jsonify(trip), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trip/<int:trip_id>", methods=["DELETE"])
def delete_trip_route(trip_id):
    user = _auth(request)
    if not user:
        return jsonify({"error": "Login required"}), 401
    try:
        delete_trip(trip_id, user["email"])
        return jsonify({"message": "Trip deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════════════════════
#  DEV UTILS
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/api/run_checks_now", methods=["GET"])
def run_checks_now():
    admin_token = os.getenv("CHECKS_ADMIN_TOKEN", "").strip()
    supplied = request.headers.get("X-Admin-Token", "").strip()
    if not admin_token or supplied != admin_token:
        return jsonify({"error": "Not found"}), 404
    try:
        check_all_trips()
        return jsonify({"message": "Checks complete — see terminal."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Avoid starting a second APScheduler instance in Flask's debug reloader.
    app.run(debug=True, port=5000, use_reloader=False)
