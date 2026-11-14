import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import database
import scheduler


class AlertMonitoringTests(unittest.TestCase):
    def test_event_hash_ignores_result_order_and_snippet_changes(self):
        first = "- Jaipur Literature Festival: First short description\n- Desert Festival: Details A"
        second = "- Desert Festival: Updated snippet\n- Jaipur Literature Festival: Different snippet"
        self.assertEqual(scheduler._event_hash(first), scheduler._event_hash(second))

    def test_weather_changes_only_flag_material_live_changes(self):
        old = {
            "forecast_type": "live",
            "daily_forecast": [{"date": "2026-11-20", "condition": "Sunny", "temp_c": 25, "source": "live"}],
        }
        unchanged = {
            "forecast_type": "live",
            "daily_forecast": [{"date": "2026-11-20", "condition": "Cloudy", "temp_c": 27, "source": "live"}],
        }
        changed = {
            "forecast_type": "live",
            "daily_forecast": [{"date": "2026-11-20", "condition": "Rainy", "temp_c": 30, "source": "live"}],
        }
        seasonal = {"forecast_type": "seasonal", "daily_forecast": old["daily_forecast"]}
        self.assertEqual(scheduler._weather_changes(old, unchanged), [])
        self.assertEqual(len(scheduler._weather_changes(old, changed)), 1)
        self.assertEqual(scheduler._weather_changes(old, seasonal), [])

    @patch.object(scheduler, "update_monitoring_state")
    @patch.object(scheduler, "send_alert", return_value=True)
    @patch.object(scheduler.itinerary_agent, "_fetch_events", return_value="- Jaipur Literature Festival: dates")
    @patch.object(scheduler.weather_agent, "get_weather", return_value={"forecast_type": "seasonal"})
    def test_first_event_check_establishes_baseline_without_alert(
        self, weather, events, send, update
    ):
        trip = {
            "id": 1, "email": "person@example.com", "destination": "Jaipur",
            "duration": 3, "start_date": "2026-11-20", "end_date": "2026-11-22",
            "baseline_weather": "{}", "last_weather_snapshot": "{}",
            "last_event_hash": "", "weather_alerts": 0, "event_alerts": 1,
        }
        scheduler.check_trip(trip)
        send.assert_not_called()
        update.assert_called_once()
        self.assertTrue(update.call_args.kwargs["last_event_hash"])
        events.assert_called_once_with("Jaipur", "2026-11-20", "2026-11-22")
        weather.assert_not_called()

    @patch.object(scheduler, "update_monitoring_state")
    @patch.object(scheduler, "send_alert", return_value=False)
    @patch.object(scheduler.itinerary_agent, "_fetch_events", return_value="No event data")
    @patch.object(scheduler.weather_agent, "get_weather")
    def test_failed_weather_email_does_not_advance_weather_baseline(
        self, weather, events, send, update
    ):
        previous = {
            "forecast_type": "live",
            "daily_forecast": [{"date": "2026-11-20", "condition": "Sunny", "temp_c": 22, "source": "live"}],
        }
        current = {
            "forecast_type": "live", "advice": "Rain expected",
            "daily_forecast": [{"date": "2026-11-20", "condition": "Rainy", "temp_c": 28, "source": "live"}],
        }
        weather.return_value = current
        trip = {
            "id": 2, "email": "person@example.com", "destination": "Jaipur",
            "duration": 1, "start_date": "2026-11-20", "end_date": "2026-11-20",
            "baseline_weather": json.dumps(previous),
            "last_weather_snapshot": json.dumps(previous),
            "last_event_hash": "", "weather_alerts": 1, "event_alerts": 0,
        }
        scheduler.check_trip(trip)
        send.assert_called_once()
        events.assert_not_called()
        self.assertIsNone(update.call_args.kwargs["last_weather_snapshot"])

    def test_existing_database_receives_alert_columns_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "legacy.db")
            con = sqlite3.connect(db_path)
            con.execute("""CREATE TABLE saved_trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                email TEXT NOT NULL, destination TEXT NOT NULL,
                duration INTEGER NOT NULL DEFAULT 5, start_date TEXT, end_date TEXT,
                travel_details TEXT NOT NULL DEFAULT '{}',
                baseline_weather TEXT NOT NULL DEFAULT '{}',
                full_plan TEXT NOT NULL DEFAULT '{}', last_event_hash TEXT DEFAULT '',
                last_checked TEXT DEFAULT (datetime('now')),
                created_at TEXT DEFAULT (datetime('now'))
            )""")
            con.execute("INSERT INTO saved_trips (email, destination, duration) VALUES (?, ?, ?)",
                        ("person@example.com", "Jaipur", 2))
            con.commit()
            con.close()
            with patch.object(database, "DB_PATH", db_path):
                database.init_db()
                con = sqlite3.connect(db_path)
                cols = {row[1] for row in con.execute("PRAGMA table_info(saved_trips)")}
                row = con.execute("SELECT email, destination, weather_alerts, event_alerts FROM saved_trips").fetchone()
                con.close()
                self.assertTrue({"last_weather_snapshot", "weather_alerts", "event_alerts"}.issubset(cols))
                self.assertEqual(row, ("person@example.com", "Jaipur", 1, 1))

    def test_database_migration_and_alert_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "trips.db")
            with patch.object(database, "DB_PATH", db_path):
                database.init_db()
                trip_id = database.save_trip(
                    "person@example.com", "Jaipur", 2, {}, {"forecast_type": "seasonal"},
                    {}, "2026-11-20", "2026-11-21", None, False, True,
                )
                con = sqlite3.connect(db_path)
                row = con.execute(
                    "SELECT weather_alerts, event_alerts, last_weather_snapshot FROM saved_trips WHERE id=?",
                    (trip_id,),
                ).fetchone()
                con.close()
                self.assertEqual(row[0:2], (0, 1))
                self.assertEqual(json.loads(row[2])["forecast_type"], "seasonal")


if __name__ == "__main__":
    unittest.main()
