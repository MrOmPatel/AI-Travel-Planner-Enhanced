"""
BudgetAllocator  —  computes per-category spending envelopes from total INR budget.

Fixed split (adjustable by travel_type):
  Accommodation  35%
  Food           25%
  Activities     15%
  Transport      12%
  Misc            8%
  Buffer          5%   (kept in reserve so total never exceeds 100%)

Returns concrete rupee ceilings that every downstream agent uses.
"""

SPLITS = {
    "default":   dict(accommodation=0.35, food=0.25, activities=0.15, transport=0.12, misc=0.08),
    "Adventure": dict(accommodation=0.30, food=0.20, activities=0.25, transport=0.15, misc=0.05),
    "Relaxation":dict(accommodation=0.40, food=0.25, activities=0.10, transport=0.10, misc=0.10),
    "Business":  dict(accommodation=0.45, food=0.25, activities=0.08, transport=0.15, misc=0.07),
    "Family":    dict(accommodation=0.35, food=0.28, activities=0.18, transport=0.12, misc=0.07),
    "Romantic":  dict(accommodation=0.40, food=0.28, activities=0.12, transport=0.10, misc=0.05),
}

def allocate(budget_inr: float, duration: int, travelers: int,
             travel_type: str = "default") -> dict:
    """
    Returns dict with:
      total_inr, accommodation_total, accommodation_per_night,
      food_total, food_per_day_per_person,
      activities_total, activities_per_day,
      transport_total, misc_total,
      meal_budget_per_person (single meal),
      hotel_max_per_night
    """
    split = SPLITS.get(travel_type, SPLITS["default"])

    # usable = 95% of total (5% buffer so we never go over)
    usable = budget_inr * 0.95

    acc_total  = round(usable * split["accommodation"], 2)
    food_total = round(usable * split["food"],          2)
    act_total  = round(usable * split["activities"],    2)
    trn_total  = round(usable * split["transport"],     2)
    msc_total  = round(usable * split["misc"],          2)

    nights  = max(duration, 1)
    pax     = max(travelers, 1)
    meals_per_day = 3

    return {
        "total_inr":               round(budget_inr, 2),
        "usable_inr":              round(usable, 2),
        # Accommodation
        "accommodation_total":     acc_total,
        "accommodation_per_night": round(acc_total / nights, 2),
        "hotel_max_per_night":     round(acc_total / nights, 2),
        # Food
        "food_total":              food_total,
        "food_per_day":            round(food_total / nights, 2),
        "food_per_day_per_person": round(food_total / nights / pax, 2),
        "meal_budget_per_person":  round(food_total / nights / meals_per_day / pax, 2),
        # Activities
        "activities_total":        act_total,
        "activities_per_day":      round(act_total / nights, 2),
        "max_entry_fee_per_place": round(act_total / nights / 3, 2),   # max 3 paid places/day
        # Transport + misc
        "transport_total":         trn_total,
        "misc_total":              msc_total,
        # Splits used (for transparency)
        "splits":                  split,
    }
