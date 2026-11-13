from flask import Flask, request, jsonify
from flask_cors import CORS
from workflow import TravelPlanWorkflow
from database import init_db, save_trip, get_all_trips, get_trips_by_email, delete_trip
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
    try:
        data = request.get_json()
        user_input = data.get("user_input", "").strip()
        if not user_input:
            return jsonify({"error": "user_input is required"}), 400
        result = workflow.plan_travel(user_input)
        if result.get("error"):
            return jsonify({"error": result["error"]}), 500
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reoptimize_day", methods=["OPTIONS", "POST"])
def reoptimize_day():
    if request.method == "OPTIONS": return "", 204
    try:
        body = request.get_json()
        updated_day = workflow.reoptimize_day(
            int(body.get("day_number", 1)),
            body.get("removed_attraction", ""),
            body.get("travel_details", {}),
            body.get("places", []),
            body.get("restaurants", []),
            body.get("weather", {}),
            used_places=body.get("used_places", [])
        )
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
        body = request.get_json()

        email      = (user["email"] if user else body.get("email", "")).strip()
        user_id    = user["user_id"] if user else None
        destination     = body.get("destination", "").strip()
        duration        = int(body.get("duration", 5))
        travel_details  = body.get("travel_details", {})
        baseline_weather= body.get("weather", {})
        full_plan       = body.get("full_plan", {})
        start_date      = body.get("start_date", "")   # "YYYY-MM-DD"
        end_date        = body.get("end_date", "")     # "YYYY-MM-DD"

        if not email or "@" not in email:
            return jsonify({"error": "Valid email required"}), 400
        if not destination:
            return jsonify({"error": "Destination required"}), 400

        trip_id = save_trip(
            email, destination, duration,
            travel_details, baseline_weather,
            full_plan, start_date, end_date, user_id
        )

        send_test_email(email)

        return jsonify({
            "message": "Trip saved! Confirmation email sent to " + email + ". You'll get weather and event alerts every 6 hours.",
            "trip_id": trip_id
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
        trips = get_trips_by_email(user["email"])
        # Strip full_plan from past trips — only send overview fields
        for t in trips:
            if t["status"] == "past":
                fp = t.get("full_plan", {})
                # Build a lightweight summary
                places = fp.get("places", [])
                t["overview_data"] = {
                    "places_visited":  [p.get("name") for p in places],
                    "total_days":      t.get("duration"),
                    "destination":     t.get("destination"),
                    "budget_inr":      fp.get("travel_details", {}).get("budget_inr"),
                    "budget_breakdown":fp.get("budget_breakdown", {}),
                    "highlights":      [p.get("name") for p in places[:4]],
                    "hotel_stayed":    fp.get("hotels", [{}])[0].get("name") if fp.get("hotels") else None,
                }
                del t["full_plan"]   # don't send full data for past trips
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
        trips = get_trips_by_email(user["email"])
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
    try:
        check_all_trips()
        return jsonify({"message": "Checks complete — see terminal."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
