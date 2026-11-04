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


def test_budget_too_low_names_the_number():
    out = find_conflicts(ctx(budget=10))
    assert len(out) == 1 and "budget" in out[0].lower() and "Raise your budget to at least $" in out[0]


def test_time_conflict_names_day():
    # vegan + gluten-free leaves no zero-minute options, so a 1-minute Monday is impossible
    out = find_conflicts(ctx(restrictions=["vegan", "gluten_free"], days=[DayCtx(0, 1)] + [DayCtx(i, 45) for i in range(1, 7)]))
    assert any(o.startswith("Monday") for o in out)


def test_goal_conflict():
    out = find_conflicts(ctx(goal="calorie_target", calorie_target=5000))
    assert any("5000" in o for o in out)


def test_restrictions_leave_nothing():
    out = find_conflicts(ctx(restrictions=["vegan", "gluten_free", "nut_allergy"], excluded=["rice", "beans", "tofu", "oats", "banana", "spinach", "chickpea", "lentil", "tomato", "potato", "avocado", "broccoli"]))
    assert out and "leave no" in out[0]


def test_multiple_conflicts_reported_together():
    out = find_conflicts(ctx(budget=10, restrictions=["vegan", "gluten_free"], days=[DayCtx(0, 1)] + [DayCtx(i, 45) for i in range(1, 7)]))
    assert len(out) >= 2


def test_ui_shows_conflicts_and_no_plan(client):
    signup(client)
    client.post("/survey", data={"budget": "10"})
    r = client.post("/plan/generate")
    assert "too low" in r.text and "Edit your survey" in r.text
    with client.app.state.session_factory() as s:
        assert s.query(Plan).count() == 0
    assert "too low" not in client.get("/").text  # message shown once
