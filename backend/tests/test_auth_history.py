import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import auth
import database


class AuthHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "test.db")
        self.db_patch = patch.object(database, "DB_PATH", self.db_path)
        self.auth_db_patch = patch.object(auth, "DB_PATH", self.db_path)
        self.db_patch.start(); self.auth_db_patch.start()
        database.init_db()
        auth.init_users_db()

    def tearDown(self):
        self.auth_db_patch.stop(); self.db_patch.stop()
        self.tmp.cleanup()

    def test_signup_login_and_logout(self):
        created = auth.signup("Person@Example.com", "Person", "password123")
        self.assertIn("token", created)
        self.assertEqual(created["email"], "person@example.com")
        self.assertIsNotNone(auth.verify_token(created["token"]))
        logged_in = auth.login("PERSON@example.com", "password123")
        self.assertIn("token", logged_in)
        self.assertIn("error", auth.login("person@example.com", "wrong"))
        auth.logout(created["token"])
        self.assertIsNone(auth.verify_token(created["token"]))

    def test_passwords_use_pbkdf2_and_legacy_passwords_upgrade(self):
        created = auth.signup("new@example.com", "New", "password123")
        con = sqlite3.connect(self.db_path)
        stored = con.execute("SELECT password_h FROM users WHERE email=?", ("new@example.com",)).fetchone()[0]
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        salt = "a1" * 16
        import hashlib
        legacy = hashlib.sha256((salt + "legacy-pass").encode()).hexdigest()
        con.execute("INSERT INTO users (email,name,salt,password_h) VALUES (?,?,?,?)",
                    ("legacy@example.com", "Legacy", salt, legacy))
        con.commit(); con.close()
        self.assertIn("token", auth.login("legacy@example.com", "legacy-pass"))
        con = sqlite3.connect(self.db_path)
        upgraded = con.execute("SELECT password_h FROM users WHERE email=?", ("legacy@example.com",)).fetchone()[0]
        con.close()
        self.assertTrue(upgraded.startswith("pbkdf2_sha256$"))

    def test_trip_history_is_account_scoped_and_full_plan_can_be_updated(self):
        user = auth.signup("owner@example.com", "Owner", "password123")
        trip_id = database.save_trip("owner@example.com", "Jaipur", 2, {}, {},
                                     {"itinerary": [{"day": 1, "activities": []}]},
                                     None, None, user["user_id"], False, False)
        self.assertIsNotNone(database.get_trip_by_id_for_user(trip_id, user["user_id"]))
        self.assertIsNone(database.get_trip_by_id_for_user(trip_id, user["user_id"] + 1))
        changed = {"itinerary": [{"day": 1, "activities": [{"activity": "Amber Fort"}]}]}
        self.assertTrue(database.update_trip_full_plan(trip_id, user["user_id"], changed))
        self.assertEqual(database.get_trip_by_id_for_user(trip_id, user["user_id"])["full_plan"], changed)

    def test_legacy_email_trip_is_linked_to_matching_account(self):
        database.save_trip("person@example.com", "Goa", 3, {}, {}, {}, None, None, None)
        user = auth.signup("person@example.com", "Person", "password123")
        auth.init_users_db()
        trip = database.get_trips_by_email("person@example.com")[0]
        self.assertEqual(trip["user_id"], user["user_id"])


if __name__ == "__main__":
    unittest.main()
