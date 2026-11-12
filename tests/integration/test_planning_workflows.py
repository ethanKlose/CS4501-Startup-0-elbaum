"""Survey -> preferences -> planner -> validators -> database -> rendered views."""
import json
import re
from collections import Counter

import pytest
from sqlalchemy import select

from app.models import DaySetting, Plan, Profile
from tests.integration.helpers import generate, onboard, post, shopping, snapshot

pytestmark = pytest.mark.integration


def test_complete_week_is_committed_and_matches_calendar_and_recipe_views(application, web):
    onboard(web, free_text="no fish, no red meat", minutes_0="60")
    page = generate(web)
    saved = snapshot(application)
    assert Counter((m["day"], m["slot"]) for m in saved["meals"]) == Counter(
        (day, slot) for day in range(7) for slot in ("breakfast", "lunch", "dinner"))
    assert saved["total_cost"] == pytest.approx(sum(m["cost"] for m in saved["meals"]), abs=0.01)
    assert saved["settings"]["checkout_total"] <= 200
    names = [i["name"].lower() for m in saved["meals"] for i in m["ingredients"]]
    assert not any(word in name for name in names for word in ("salmon", "tuna", "beef", "pork"))
    embedded = json.loads(re.search(r'<script[^>]*id="meals-data"[^>]*>(.*?)</script>', page.text, re.S)[1])
    assert {int(key) for key in embedded} == {m["id"] for m in saved["meals"]}
    meal = saved["meals"][0]
    recipe = web.get(f'/meals/{meal["id"]}')
    assert recipe.status_code == 200 and meal["name"] in recipe.text
    assert 'Ingredients' in recipe.text and 'Steps' in recipe.text


def test_invalid_multisection_survey_rolls_back_all_changes(application, web):
    onboard(web, free_text="no fish", minutes_0="60", goal="high_protein")
    generate(web)
    before = snapshot(application)
    response = post(web, "/survey", {"budget": "90", "minutes_0": "1.5", "free_text": "no dairy", "goal": "none"})
    assert response.status_code == 400
    assert "Monday" in response.text
    with application.sessions() as db:
        profile = db.scalar(select(Profile))
        assert (profile.budget, profile.free_text, profile.goal) == (200, "no fish", "high_protein")
        assert db.scalar(select(DaySetting).where(DaySetting.weekday == 0)).minutes == 60
    assert snapshot(application) == before


@pytest.mark.parametrize("restriction,forbidden", [
    ("vegetarian", {"chicken", "beef", "tuna", "salmon", "pork"}),
    ("vegan", {"chicken", "beef", "tuna", "salmon", "milk", "eggs", "yogurt", "cheese"}),
    ("dairy_free", {"milk", "yogurt", "cheese"}),
    ("nut_allergy", {"peanut", "almond", "walnut"}),
])
def test_selected_diet_survives_survey_generation_and_regeneration(application, web, restriction, forbidden):
    onboard(web, restrictions_present="1", restrictions=[restriction])
    generate(web)
    original = snapshot(application)
    generate(web, "/plan/regenerate")
    saved = snapshot(application)
    assert saved["id"] != original["id"] and len(saved["meals"]) == 21
    assert saved["settings"]["restrictions"] == [restriction]
    assert not any(term in ingredient["name"].lower() for m in saved["meals"]
                   for ingredient in m["ingredients"] for term in forbidden)
    assert web.get(f'/plans/{original["id"]}').status_code == 200


def test_kitchen_outside_meals_and_schedule_flow_into_calendar(application, web):
    onboard(web, free_text="No cooking on Wednesdays")
    assert post(web, "/preferences/lifestyle", {
        "equipment": ["microwave", "fridge", "freezer"], "cooking_skill": "beginner",
        "external_1_lunch": "1"}).status_code == 303
    assert post(web, "/preferences/schedule", {
        "time_breakfast": "07:30", "time_lunch": "13:00", "time_dinner": "20:00",
        "windows_0": "06:00-07:30,17:00-20:00"}).status_code == 303
    page = generate(web)
    saved = snapshot(application)
    assert len(saved["meals"]) == 20
    assert not any(m["day"] == 1 and m["slot"] == "lunch" for m in saved["meals"])
    assert saved["settings"]["meal_times"] == {"breakfast": 450, "lunch": 780, "dinner": 1200}
    assert saved["settings"]["cooking_windows"]["0"] == [[360, 450], [1020, 1200]]
    assert saved["settings"]["equipment"] == ["freezer", "fridge", "microwave"]
    assert all(m["cook_day"] != 2 for m in saved["meals"] if m["cook_minutes"])
    assert "Dining hall / eating elsewhere" in page.text
    calendar = web.get(f'/plans/{saved["id"]}/calendar.ics').text
    assert "SUMMARY:Dining hall / eating elsewhere" in calendar
    assert "T130000" in calendar


def test_plan_from_today_removes_elapsed_slots_and_never_schedules_past_prep(application, web):
    onboard(web)
    generate(web)
    future = snapshot(application)
    generate(web, start_mode="today")
    current = snapshot(application)
    assert future["settings"]["week_start"] == "2026-11-09"
    assert current["settings"]["week_start"] == "2026-11-02"
    assert len(current["meals"]) == 20
    assert not any(m["day"] == 0 and m["slot"] == "breakfast" for m in current["meals"])
    assert all(m["cook_day"] >= 0 for m in current["meals"] if m["cook_minutes"])
    calendar = web.get(f'/plans/{current["id"]}/calendar.ics').text
    starts = re.findall(r"^DTSTART[^:]*:(\d{8}T\d{6})", calendar, re.M)
    assert starts and min(starts) >= "20261102T090100"


def test_outside_nutrition_goal_is_visible_as_warning_not_unconditional_success(application, web):
    onboard(web, goal="calorie_target", calorie_target="2000")
    assert post(web, "/preferences/lifestyle", {"equipment": ["stove", "fridge", "freezer"], "external_1_lunch": "1"}).status_code == 303
    page = generate(web)
    saved = snapshot(application)
    assert saved["attempts"] == 3
    assert any("cannot be verified" in warning for warning in saved["warnings"])
    assert "Needs review" in page.text and "full-day nutrition" in page.text


def test_local_prices_and_pantry_change_new_plan_without_rewriting_history(application, web):
    onboard(web)
    generate(web)
    original = snapshot(application)
    assert post(web, "/pantry/add", {"name": "rice", "quantity": "100", "unit": "cup"}).status_code == 303
    assert post(web, "/prices", {"key": "rice|cup", "quantity": "4", "price": "2.99",
                                "source": "Integration receipt", "observed_on": "2026-11-01"}).status_code == 303
    generate(web, "/plan/regenerate")
    saved = snapshot(application)
    assert saved["settings"]["price_offers"]["rice|cup"]["package_price"] == 2.99
    assert saved["settings"]["pantry"] == [{"name": "rice", "quantity": 100, "unit": "cup"}]
    assert "Integration receipt" in web.get("/prices").text
    assert "rice|cup" not in {item["key"] for item in shopping(application, saved["id"])}
    with application.sessions() as db:
        old = db.get(Plan, original["id"])
        assert old.settings.get("price_offers") == original["settings"].get("price_offers")
        assert [m.as_dict() for m in old.meals] == [
            {k: v for k, v in m.items() if k not in {"id", "status", "rating", "pinned", "cook_day", "frozen"}}
            for m in original["meals"]]


def test_pins_swaps_skips_and_restore_keep_calendar_and_groceries_consistent(application, web):
    from tests.integration.helpers import shopping
    onboard(web)
    generate(web)
    first = snapshot(application)
    pin = first["meals"][0]
    assert post(web, f'/meals/{pin["id"]}/pin').status_code == 303
    assert post(web, "/plan/days/3/skip").status_code == 303
    generate(web, "/plan/regenerate")
    saved = snapshot(application)
    pinned = next(m for m in saved["meals"] if m["pinned"])
    assert (pinned["name"], pinned["ingredients"], pinned["steps"]) == (pin["name"], pin["ingredients"], pin["steps"])
    assert len(saved["meals"]) == 18 and all(m["day"] != 3 for m in saved["meals"])
    other = saved["meals"][-1]
    assert post(web, f'/meals/{other["id"]}/swap').status_code == 303
    swapped = snapshot(application)
    assert next(m for m in swapped["meals"] if m["id"] == other["id"])["name"] != other["name"]
    # A swap can rebalance batch preparation; other recipes and user history stay.
    def recipes(meals):
        return {m["id"]: {k: v for k, v in m.items() if k not in {"cook_day", "frozen"}}
                for m in meals if m["id"] != other["id"]}
    assert recipes(saved["meals"]) == recipes(swapped["meals"])
    expected = Counter()
    for meal in swapped["meals"]:
        for item in meal["ingredients"]:
            expected[(item["name"].strip().lower(), item["unit"].strip().lower())] += item["quantity"]
    actual = {(i["name"], i["unit"]): i["quantity"] for i in shopping(application, swapped["id"])}
    assert actual == pytest.approx(dict(expected), abs=0.02)
    assert post(web, "/plan/days/3/skip").status_code == 303
    generate(web, "/plan/regenerate")
    assert len(snapshot(application)["meals"]) == 21
