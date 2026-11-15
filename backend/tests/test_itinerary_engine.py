import unittest
from unittest.mock import patch
import algorithms
from algorithms import run_algorithm_pipeline


class ItineraryEngineTests(unittest.TestCase):
    def setUp(self):
        self.env = {"activities_per_day": 100, "activities_total": 300}
        self.td = {
            "destination": "Rajasthan", "duration": 3, "travelers": 2,
            "start_date": "2026-11-13", "interests": ["heritage"]
        }

    def test_all_fetched_places_are_surfaced_once_and_geo_grouped(self):
        places = []
        cities = [
            ("Jaipur", 26.9124, 75.7873, 5),
            ("Jodhpur", 26.2389, 73.0243, 4),
            ("Udaipur", 24.5854, 73.7125, 4),
        ]
        for city, lat, lon, count in cities:
            for i in range(count):
                places.append({
                    "name": f"{city} attraction {i}",
                    "location": city, "lat": lat + i * .001,
                    "lon": lon + i * .001, "coordinates_verified": True, "open_time": "09:00",
                    "close_time": "18:00", "visit_duration_hrs": 1,
                    "entry_fee_inr": 0, "is_outdoor": True, "rating": 4.5,
                })
        days = run_algorithm_pipeline(places, [], self.td, {}, self.env)
        surfaced = []
        for day in days:
            surfaced += [a["activity"] for a in day["activities"]]
            surfaced += [p["name"] for p in day["additional_places"]]
        self.assertEqual(len(surfaced), len(places))
        self.assertEqual(len(set(surfaced)), len(places))
        self.assertEqual(len(days), 3)
        # Each synthetic city should remain within a single daily group.
        for day in days:
            city_names = {name.split()[0] for name in day["all_place_names"]}
            self.assertLessEqual(len(city_names), 1)

    def test_budget_and_weather_are_warnings_not_exclusions(self):
        places = [{
            "name": "Expensive outdoor place", "location": "Jaipur",
            "lat": 26.9, "lon": 75.8, "coordinates_verified": True, "open_time": "09:00",
            "close_time": "18:00", "visit_duration_hrs": 1,
            "entry_fee_inr": 5000, "is_outdoor": True, "rating": 4.5,
        }]
        weather = {"data_available": True, "daily_forecast": [{
            "date": "2026-11-13", "is_outdoor_ok": False,
            "advice": "Rain expected"
        }]}
        day = run_algorithm_pipeline(places, [], {**self.td, "duration": 1},
                                     weather, {"activities_per_day": 1})[0]
        self.assertEqual(day["activities"][0]["activity"], "Expensive outdoor place")
        caution = day["activities"][0]["caution"]
        self.assertIn("Weather advisory", caution)
        self.assertIn("Budget advisory", caution)

    def test_arrival_before_close_allows_short_visit_but_at_or_after_close_is_not_scheduled(self):
        places = [
            {"name": "Short visit", "location": "Jaipur", "lat": 26.9, "lon": 75.8, "coordinates_verified": True,
             "open_time": "09:00", "close_time": "09:30",
             "visit_duration_hrs": 2, "entry_fee_inr": 0, "is_outdoor": False},
            {"name": "Already closed", "location": "Jaipur", "lat": 26.91, "lon": 75.81, "coordinates_verified": True,
             "open_time": "08:00", "close_time": "08:30",
             "visit_duration_hrs": 1, "entry_fee_inr": 0, "is_outdoor": False},
        ]
        day = run_algorithm_pipeline(places, [], {**self.td, "duration": 1},
                                     {}, self.env)[0]
        scheduled = {a["activity"]: a for a in day["activities"]}
        additional = {p["name"]: p for p in day["additional_places"]}
        self.assertIn("Short visit", scheduled)
        self.assertIn("Limited visiting time", scheduled["Short visit"]["caution"])
        self.assertNotIn("Already closed", scheduled)
        self.assertIn("Already closed", additional)
        self.assertEqual(additional["Already closed"]["schedule_status"], "closed_before_arrival")
        self.assertIn("at or after entry closing time", additional["Already closed"]["reason"])


    def test_arrival_exactly_at_entry_closing_is_not_scheduled(self):
        places = [{
            "name": "Closes at arrival", "location": "Jaipur",
            "lat": 26.9, "lon": 75.8, "coordinates_verified": True,
            "open_time": "08:00", "close_time": "09:00",
            "visit_duration_hrs": 1, "entry_fee_inr": 0, "is_outdoor": False,
        }]
        day = run_algorithm_pipeline(places, [], {**self.td, "duration": 1}, {}, self.env)[0]
        self.assertFalse(any(a["activity"] == "Closes at arrival" for a in day["activities"]))
        item = next(p for p in day["additional_places"] if p["name"] == "Closes at arrival")
        self.assertEqual(item["schedule_status"], "closed_before_arrival")

    def test_empty_day_uses_nearest_remaining_verified_area_with_transfer_warning(self):
        places = [
            {"name": "Jaipur A", "location": "Jaipur", "lat": 26.9000, "lon": 75.8000,
             "coordinates_verified": True, "open_time": "09:00", "close_time": "18:00",
             "visit_duration_hrs": 1, "rating": 5},
            {"name": "Jaipur B", "location": "Jaipur", "lat": 26.9010, "lon": 75.8010,
             "coordinates_verified": True, "open_time": "09:00", "close_time": "18:00",
             "visit_duration_hrs": 1, "rating": 5},
            {"name": "Closed Pushkar stop", "location": "Pushkar", "lat": 26.4873, "lon": 74.5489,
             "coordinates_verified": True, "open_time": "08:00", "close_time": "08:30",
             "visit_duration_hrs": 1, "rating": 4.9},
            {"name": "Udaipur stop", "location": "Udaipur", "lat": 24.5854, "lon": 73.7125,
             "coordinates_verified": True, "open_time": "09:00", "close_time": "18:00",
             "visit_duration_hrs": 1, "rating": 4.8},
            {"name": "Jodhpur fallback", "location": "Jodhpur", "lat": 26.2389, "lon": 73.0243,
             "coordinates_verified": True, "open_time": "09:00", "close_time": "18:00",
             "visit_duration_hrs": 1, "rating": 4.7},
        ]
        days = run_algorithm_pipeline(places, [], {**self.td, "duration": 3}, {}, self.env)
        scheduled = [[a["activity"] for a in day["activities"]] for day in days]
        surfaced = [a["activity"] for day in days for a in day["activities"]]
        surfaced += [p["name"] for day in days for p in day["additional_places"]]
        self.assertIn("Jodhpur fallback", surfaced)
        all_scheduled = [name for names in scheduled for name in names]
        self.assertEqual(len(all_scheduled), len(set(all_scheduled)))


    def test_final_fallback_does_not_randomly_schedule_unverified_place_without_locality_match(self):
        first = {
            "name": "Scheduled Jaipur attraction", "location": "Jaipur",
            "lat": 26.9, "lon": 75.8, "coordinates_verified": True,
            "open_time": "09:00", "close_time": "18:00",
            "visit_duration_hrs": 1, "rating": 5,
        }
        fallback = {
            "name": "Ponda standalone attraction", "location": "Ponda, Goa",
            "lat": 0, "lon": 0, "coordinates_verified": False,
            "open_time": "09:00", "close_time": "18:00",
            "visit_duration_hrs": 1, "rating": 4.8,
        }
        # Force the second day to be empty and the Ponda attraction to be
        # outside the selected daily groups, as can happen with clustering.
        with patch.object(algorithms, "_balanced_geo_groups",
                          return_value=([[first], []], [fallback])):
            days = run_algorithm_pipeline(
                [first, fallback], [], {**self.td, "duration": 2}, {}, self.env
            )
        self.assertEqual(days[0]["activities"][0]["activity"], "Scheduled Jaipur attraction")
        self.assertFalse(days[1]["activities"])
        self.assertTrue(any(
            p.get("name") == "Ponda standalone attraction"
            for day in days for p in day["additional_places"]
        ))

    def test_restaurants_are_not_inserted_into_daily_route(self):
        places = [{
            "name": "Attraction", "location": "Jaipur", "lat": 26.9, "lon": 75.8, "coordinates_verified": True,
            "open_time": "09:00", "close_time": "18:00",
            "visit_duration_hrs": 1, "entry_fee_inr": 0,
        }]
        restaurants = [{"name": "Restaurant name", "location": "Far away"}]
        day = run_algorithm_pipeline(places, restaurants,
                                     {**self.td, "duration": 1}, {}, self.env)[0]
        self.assertEqual([a["activity"] for a in day["activities"]], ["Attraction"])
        self.assertIn("Restaurant Recommendations", day["meals"]["lunch"])

    def test_unverified_coordinates_are_scheduled_as_standalone_with_warning(self):
        places = [{
            "name": "Unverified attraction", "location": "Jaipur",
            "lat": 26.9, "lon": 75.8, "coordinates_verified": False,
            "open_time": "09:00", "close_time": "18:00",
            "visit_duration_hrs": 1, "entry_fee_inr": 0,
        }]
        day = run_algorithm_pipeline(places, [], {**self.td, "duration": 1}, {}, self.env)[0]
        self.assertEqual(len(day["activities"]), 1)
        self.assertEqual(day["activities"][0]["activity"], "Unverified attraction")
        self.assertIn("Location not verified", day["activities"][0]["caution"])
        self.assertIn("No route time or distance is estimated", day["activities"][0]["travel_note"])

    def test_unverified_attraction_from_unselected_city_is_not_randomly_scheduled(self):
        places = [
            {
                "name": "Verified Jaipur attraction", "location": "Jaipur, Rajasthan",
                "lat": 26.9, "lon": 75.8, "coordinates_verified": True,
                "open_time": "09:00", "close_time": "18:00",
                "visit_duration_hrs": 1, "rating": 5,
            },
            {
                "name": "Unverified Goa attraction", "location": "Goa, India",
                "lat": 0, "lon": 0, "coordinates_verified": False,
                "open_time": "09:00", "close_time": "18:00",
                "visit_duration_hrs": 1, "rating": 4.9,
            },
        ]
        days = run_algorithm_pipeline(
            places, [], {**self.td, "duration": 1}, {}, self.env
        )
        scheduled = [
            activity for day in days for activity in day["activities"]
        ]
        self.assertEqual(
            {activity["activity"] for activity in scheduled},
            {"Verified Jaipur attraction"},
        )
        self.assertTrue(any(
            p.get("name") == "Unverified Goa attraction"
            for day in days for p in day["additional_places"]
        ))

    def test_unverified_attractions_with_same_specific_locality_are_grouped(self):
        places = [
            {"name": "Assi Ghat", "location": "Assi Ghat, Varanasi, Uttar Pradesh",
             "locality": "Assi", "lat": 0, "lon": 0, "coordinates_verified": False,
             "open_time": "05:00", "close_time": "20:00", "visit_duration_hrs": 1},
            {"name": "Tulsi Ghat", "location": "Tulsi Ghat, Assi, Varanasi",
             "locality": "Assi", "lat": 0, "lon": 0, "coordinates_verified": False,
             "open_time": "05:00", "close_time": "20:00", "visit_duration_hrs": 1},
            {"name": "Sarnath Museum", "location": "Sarnath, Varanasi",
             "locality": "Sarnath", "lat": 0, "lon": 0, "coordinates_verified": False,
             "open_time": "09:00", "close_time": "17:00", "visit_duration_hrs": 1},
        ]
        groups, unselected = algorithms._balanced_geo_groups(
            places, 3, return_unselected=True
        )
        self.assertEqual(len(groups), 3)
        self.assertTrue(any(
            {p["name"] for p in group} >= {"Assi Ghat", "Tulsi Ghat"}
            for group in groups
        ))
        self.assertEqual(unselected, [])

    def test_same_attraction_name_does_not_override_different_localities(self):
        first = {"name": "Shiv Temple", "location": "Old City, Jaipur",
                 "locality": "Old City", "coordinates_verified": False}
        second = {"name": "Shiv Temple", "location": "Sarnath, Varanasi",
                  "locality": "Sarnath", "coordinates_verified": False}
        self.assertFalse(algorithms._localities_match(first, second))

    def test_distant_cities_are_not_mixed_into_one_day(self):
        places = [
            {"name": "Jaipur attraction", "location": "Jaipur, Rajasthan",
             "lat": 26.9239, "lon": 75.8268, "coordinates_verified": True,
             "open_time": "09:00", "close_time": "18:00", "visit_duration_hrs": 1,
             "entry_fee_inr": 0, "rating": 4.8},
            {"name": "Pushkar attraction", "location": "Pushkar, Rajasthan",
             "lat": 26.4873, "lon": 74.5489, "coordinates_verified": True,
             "open_time": "09:00", "close_time": "18:00", "visit_duration_hrs": 1,
             "entry_fee_inr": 0, "rating": 4.7},
        ]
        day = run_algorithm_pipeline(places, [], {**self.td, "duration": 1}, {}, self.env)[0]
        scheduled = [a["activity"] for a in day["activities"]]
        additional = {p["name"]: p for p in day["additional_places"]}
        self.assertEqual(len(scheduled), 1)
        self.assertIn("Pushkar attraction", additional)
        self.assertEqual(additional["Pushkar attraction"]["schedule_status"], "outside_daily_area")
        self.assertEqual(day["route_warnings"], [])

    def test_unverified_places_in_selected_city_are_scheduled_standalone(self):
        places = [
            {"name": "Verified Jaipur place", "location": "Jaipur, Rajasthan",
             "lat": 26.9239, "lon": 75.8268, "coordinates_verified": True,
             "open_time": "09:00", "close_time": "18:00", "visit_duration_hrs": 1,
             "entry_fee_inr": 0, "rating": 4.8},
            {"name": "Unverified Jaipur place", "location": "Jaipur, Rajasthan",
             "lat": 0, "lon": 0, "coordinates_verified": False,
             "open_time": "09:00", "close_time": "18:00", "visit_duration_hrs": 1,
             "entry_fee_inr": 0, "rating": 4.7},
        ]
        day = run_algorithm_pipeline(places, [], {**self.td, "duration": 1}, {}, self.env)[0]
        scheduled = [a["activity"] for a in day["activities"]]
        self.assertIn("Verified Jaipur place", scheduled)
        self.assertIn("Unverified Jaipur place", scheduled)
        unverified = next(a for a in day["activities"] if a["activity"] == "Unverified Jaipur place")
        self.assertIn("Location not verified", unverified["caution"])

    def test_same_locality_label_cannot_force_a_long_route_leg(self):
        places = [
            {"name": "First stop", "location": "Rajasthan, India",
             "lat": 26.9239, "lon": 75.8268, "coordinates_verified": True,
             "open_time": "09:00", "close_time": "18:00", "visit_duration_hrs": 1,
             "entry_fee_inr": 0, "rating": 4.8},
            {"name": "Distant stop", "location": "Rajasthan, India",
             "lat": 24.5696, "lon": 73.6722, "coordinates_verified": True,
             "open_time": "09:00", "close_time": "18:00", "visit_duration_hrs": 1,
             "entry_fee_inr": 0, "rating": 4.7},
        ]
        day = run_algorithm_pipeline(places, [], {**self.td, "duration": 1}, {}, self.env)[0]
        self.assertLessEqual(len(day["activities"]), 1)
        self.assertTrue(any(p["name"] == "Distant stop" for p in day["additional_places"]))
        self.assertEqual(day["route_warnings"], [])


if __name__ == "__main__":
    unittest.main()
