import sqlite3, json, os
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(__file__), "trips.db")


def init_db():
    con = sqlite3.connect(DB_PATH)
    # saved_trips — now stores full plan + user auth + travel dates
    con.execute("""
        CREATE TABLE IF NOT EXISTS saved_trips (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER,
            email            TEXT    NOT NULL,
            destination      TEXT    NOT NULL,
            duration         INTEGER NOT NULL DEFAULT 5,
            start_date       TEXT,
            end_date         TEXT,
            travel_details   TEXT    NOT NULL DEFAULT '{}',
            baseline_weather TEXT    NOT NULL DEFAULT '{}',
            full_plan        TEXT    NOT NULL DEFAULT '{}',
            last_event_hash  TEXT    DEFAULT '',
            last_checked     TEXT    DEFAULT (datetime('now')),
            created_at       TEXT    DEFAULT (datetime('now'))
        )
    """)
    # Add new columns to existing DB if upgrading from old version
    cols = [r[1] for r in con.execute("PRAGMA table_info(saved_trips)").fetchall()]
    for col, defn in [
        ("start_date",  "TEXT DEFAULT NULL"),
        ("end_date",    "TEXT DEFAULT NULL"),
        ("full_plan",   "TEXT DEFAULT '{}'"),
        ("user_id",     "INTEGER DEFAULT NULL"),
    ]:
        if col not in cols:
            con.execute("ALTER TABLE saved_trips ADD COLUMN " + col + " " + defn)
    con.commit()
    con.close()
    print("Database ready: " + DB_PATH)


def save_trip(email: str, destination: str, duration: int,
              travel_details: dict, baseline_weather: dict,
              full_plan: dict = None,
              start_date: str = None, end_date: str = None,
              user_id: int = None) -> int:
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(
        """INSERT INTO saved_trips
           (email, destination, duration, travel_details, baseline_weather,
            full_plan, start_date, end_date, user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (email.strip().lower(), destination, duration,
         json.dumps(travel_details), json.dumps(baseline_weather),
         json.dumps(full_plan or {}),
         start_date, end_date, user_id)
    )
    trip_id = cur.lastrowid
    con.commit(); con.close()
    print("Trip saved: id=" + str(trip_id) + " dest=" + destination)
    return trip_id


def get_trips_by_email(email: str) -> list:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM saved_trips WHERE email=? ORDER BY created_at DESC",
        (email.strip().lower(),)
    ).fetchall()
    con.close()
    trips = []
    today = date.today().isoformat()
    for r in rows:
        t = dict(r)
        # Determine if trip is upcoming/active or past
        end_date = t.get("end_date") or ""
        if end_date and end_date < today:
            t["status"] = "past"
        else:
            t["status"] = "upcoming"
        # Parse JSON blobs
        for key in ("travel_details", "baseline_weather", "full_plan"):
            try:
                t[key] = json.loads(t.get(key) or "{}")
            except Exception:
                t[key] = {}
        trips.append(t)
    return trips


def get_all_trips() -> list:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM saved_trips ORDER BY id ASC").fetchall()
    con.close()
    return [dict(r) for r in rows]


def update_last_checked(trip_id: int, last_event_hash: str = None):
    con = sqlite3.connect(DB_PATH)
    if last_event_hash is not None:
        con.execute(
            "UPDATE saved_trips SET last_checked=datetime('now'), last_event_hash=? WHERE id=?",
            (last_event_hash, trip_id))
    else:
        con.execute(
            "UPDATE saved_trips SET last_checked=datetime('now') WHERE id=?",
            (trip_id,))
    con.commit(); con.close()


def delete_trip(trip_id: int, email: str):
    """Only allow deleting your own trips."""
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM saved_trips WHERE id=? AND email=?",
                (trip_id, email.strip().lower()))
    con.commit(); con.close()
