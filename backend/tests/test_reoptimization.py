import unittest
from reoptimization import filter_places_used_on_other_days


class ReoptimizationUniquenessTests(unittest.TestCase):
    def test_other_day_places_are_excluded_but_same_day_candidates_remain(self):
        candidates = [
            {"name": "Amber Fort"},
            {"name": "City Palace"},
            {"name": "Hawa Mahal"},
        ]
        # Day 1's original places are not passed as exclusions; they remain eligible.
        # Only places assigned to Day 2/3 are excluded from Day 1 re-optimization.
        available = filter_places_used_on_other_days(candidates, ["City Palace", "Hawa Mahal"])
        self.assertEqual([p["name"] for p in available], ["Amber Fort"])

    def test_name_comparison_is_case_and_whitespace_insensitive(self):
        candidates = [{"name": "  Amber   Fort "}, {"name": "City Palace"}]
        available = filter_places_used_on_other_days(candidates, ["amber fort"])
        self.assertEqual([p["name"] for p in available], ["City Palace"])

    def test_empty_other_day_list_keeps_all_candidates(self):
        candidates = [{"name": "Amber Fort"}, {"name": "City Palace"}]
        self.assertEqual(filter_places_used_on_other_days(candidates, []), candidates)


if __name__ == "__main__":
    unittest.main()
