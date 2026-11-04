from app.models import Plan
from app.services.explain import find_conflicts
from app.services.types import DayCtx, PlanContext
from tests.helpers import signup


def ctx(**kw):
    base = dict(budget=100.0, days=[DayCtx(i, 45) for i in range(7)])
    base.update(kw)
    return PlanContext(**base)


def test_feasible_has_no_conflicts():
    assert find_conflicts(ctx()) == []


def test_time_and_calories_are_never_hard_conflicts():
    # A no-cook week with a huge calorie target is a *warning* on the plan, not a reason to refuse one.
    c = ctx(days=[DayCtx(i, 0) for i in range(7)], goal="calorie_target", calorie_target=4500)
    assert find_conflicts(c) == []


def test_budget_too_low_names_the_number():
    out = find_conflicts(ctx(budget=10))
    assert len(out) == 1 and "budget" in out[0].lower() and "Raise your budget to at least $" in out[0]


def test_restrictions_leave_nothing():
    out = find_conflicts(ctx(restrictions=["vegan", "gluten_free", "nut_allergy"], excluded=["rice", "beans", "tofu", "oats", "banana", "spinach", "chickpea", "lentil", "tomato", "potato", "avocado", "broccoli", "seeds", "tempeh", "syrup", "soy"]))
    assert out and "leave no" in out[0]


def test_rated_down_meals_can_leave_nothing():
    from app.services.catalog import RECIPES

    out = find_conflicts(ctx(disliked=[r["name"] for r in RECIPES if "breakfast" in r["slots"]]))
    assert out and "leave no breakfast" in out[0]


def test_pinned_meals_over_budget():
    from app.services.catalog import RECIPES
    from app.services.llm import _recipe_to_meal

    pins = [_recipe_to_meal(RECIPES[0], 0, "breakfast") for _ in range(3)]
    for p in pins:
        p["cost"] = 50
    out = find_conflicts(ctx(pinned=pins))
    assert any("pinned meals alone cost" in o for o in out)


def test_ui_shows_conflicts_and_no_plan(client):
    signup(client)
    from tests.helpers import set_budget

    client.post("/survey", data={"budget": "50"})
    set_budget(client, 10)
    r = client.post("/plan/generate")
    assert "too low" in r.text and "Edit your survey" in r.text
    with client.app.state.session_factory() as s:
        assert s.query(Plan).count() == 0
    assert "too low" not in client.get("/").text  # message shown once
