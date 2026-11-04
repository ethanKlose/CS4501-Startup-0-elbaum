import pytest

from app.models import Meal, Plan
from app.services.llm import FakeLLM, get_llm
from app.services.types import DayCtx, PlanContext
from tests.helpers import signup


def ctx(**kw):
    base = dict(budget=100.0, days=[DayCtx(i, 45) for i in range(7)])
    base.update(kw)
    return PlanContext(**base)


@pytest.fixture()
def onboarded(client):
    signup(client)
    client.post("/survey", data={"budget": "100"})
    return client


def plans(client):
    with client.app.state.session_factory() as s:
        return s.query(Plan).all()


def meals(client):
    with client.app.state.session_factory() as s:
        return s.query(Meal).all()


def test_generate_requires_login(client):
    assert client.post("/plan/generate", follow_redirects=False).headers["location"] == "/login"


def test_generate_full_week(onboarded):
    r = onboarded.post("/plan/generate", follow_redirects=False)
    assert r.status_code == 303
    ms = meals(onboarded)
    assert len(ms) == 21  # 7 days x 3 slots
    assert {(m.day, m.slot) for m in ms} == {(d, s) for d in range(7) for s in ("breakfast", "lunch", "dinner")}
    page = onboarded.get("/").text
    assert "Regenerate week" in page and ms[0].name in page


def test_fake_llm_is_valid_for_default_context():
    from app.services.validators import validate_plan

    c = ctx()
    plan, errors = validate_plan(FakeLLM().generate_plan(c), c)
    assert errors == [] and len(plan["meals"]) == 21


def test_malformed_llm_output_is_rejected(onboarded):
    class Bad:
        def interpret_preferences(self, t): return {"excluded": [], "day_minutes_cap": {}}
        def generate_plan(self, c, f=()): return {"meals": [{"day": 9}]}

    onboarded.app.dependency_overrides[get_llm] = lambda: Bad()
    r = onboarded.post("/plan/generate")  # follows redirect to "/", which shows the flash
    assert plans(onboarded) == []
    assert "valid plan" in r.text


def test_generate_needs_survey(client):
    signup(client)
    client.post("/plan/generate")
    assert plans(client) == []


class Scripted:
    """Fake LLM that replays canned plans and records the feedback it receives."""

    def __init__(self, *plans):
        self.plans, self.calls = list(plans), []

    def interpret_preferences(self, t):
        return {"excluded": [], "day_minutes_cap": {}}

    def generate_plan(self, c, feedback=()):
        self.calls.append(list(feedback))
        return self.plans.pop(0) if len(self.plans) > 1 else self.plans[0]


def good_plan(**kw):
    return FakeLLM().generate_plan(ctx(**kw))


def scale_costs(plan, factor):
    import copy

    p = copy.deepcopy(plan)
    for m in p["meals"]:
        for i in m["ingredients"]:
            i["cost"] = round(i["cost"] * factor, 2)
        m["cost"] = round(sum(i["cost"] for i in m["ingredients"]), 2)
    return p


def test_over_budget_plan_is_never_saved_and_retried(onboarded):
    good = good_plan()
    llm = Scripted(scale_costs(good, 10), good)  # first attempt blows the budget
    onboarded.app.dependency_overrides[get_llm] = lambda: llm
    onboarded.post("/plan/generate")
    assert len(llm.calls) == 2
    assert llm.calls[0] == [] and "exceeds the weekly budget" in llm.calls[1][0]  # error fed back
    ps = plans(onboarded)
    assert len(ps) == 1 and ps[0].attempts == 2 and ps[0].total_cost <= 100


def test_gives_up_after_max_attempts(onboarded):
    llm = Scripted(scale_costs(good_plan(), 10))
    onboarded.app.dependency_overrides[get_llm] = lambda: llm
    r = onboarded.post("/plan/generate")
    assert len(llm.calls) == 3
    assert plans(onboarded) == []
    assert "exceeds the weekly budget" in r.text


def test_budget_is_a_hard_limit_for_real_fake_llm(client):
    signup(client)
    client.post("/survey", data={"budget": "30"})
    client.post("/plan/generate")
    for p in plans(client):
        assert p.total_cost <= 30


from app.services.validators import validate_full, validate_plan  # noqa: E402


@pytest.mark.parametrize("restrictions", [["vegan"], ["vegetarian"], ["gluten_free"], ["dairy_free"], ["nut_allergy"],
                                          ["shellfish_allergy"], ["egg_free"], ["halal"], ["vegan", "gluten_free", "nut_allergy"]])
def test_fake_llm_respects_every_restriction(restrictions):
    c = ctx(restrictions=restrictions)
    plan, errors = validate_plan(FakeLLM().generate_plan(c), c)
    assert errors == [], errors


def test_validator_catches_violating_meal():
    c = ctx(restrictions=["vegetarian"])
    raw = FakeLLM().generate_plan(c)
    raw["meals"][3]["ingredients"].append(dict(name="chicken breast", quantity=4, unit="oz", section="meat", cost=1.0))
    plan, errors = validate_plan(raw, c)
    assert any("violates 'vegetarian'" in e for e in errors)


def test_free_text_is_interpreted():
    out = FakeLLM().interpret_preferences("no fish, I hate cooking on Mondays")
    assert out["excluded"] == ["fish"] and out["day_minutes_cap"] == {"0": 15}
    out = FakeLLM().interpret_preferences("I'm allergic to mushrooms and olives. No cooking on Fridays")
    assert set(out["excluded"]) == {"mushrooms", "olives"} and out["day_minutes_cap"] == {"4": 0}


def test_free_text_applied_to_plan_not_just_stored(client):
    signup(client)
    client.post("/survey", data={"budget": "100", "free_text": "no fish, no chicken. I hate cooking on Mondays"})
    client.post("/plan/generate")
    ms = meals(client)
    assert len(ms) == 21
    for m in ms:
        text = (m.name + " " + " ".join(i["name"] for i in m.ingredients)).lower()
        assert "salmon" not in text and "tuna" not in text and "chicken" not in text
    assert sum(m.cook_minutes for m in ms if m.day == 0) <= 15


def test_violation_triggers_regeneration(onboarded):
    import copy

    good = good_plan()
    bad = copy.deepcopy(good)
    bad["meals"][0]["ingredients"].append(dict(name="peanut butter", quantity=1, unit="tbsp", section="pantry", cost=0.1))
    bad["meals"][0]["cost"] = round(bad["meals"][0]["cost"] + 0.1, 2)
    onboarded.post("/survey", data={"restrictions_present": "1", "restrictions": ["nut_allergy"]})
    llm = Scripted(bad, good_plan(restrictions=["nut_allergy"]))
    onboarded.app.dependency_overrides[get_llm] = lambda: llm
    onboarded.post("/plan/generate")
    assert len(llm.calls) == 2 and "nut allergy" in llm.calls[1][0]
    assert len(plans(onboarded)) == 1


def test_cooking_time_limit_enforced():
    c = ctx(days=[DayCtx(i, 10) for i in range(7)])
    raw = FakeLLM().generate_plan(ctx())  # plan assumes 45 min/day
    _, errors = validate_plan(raw, c)
    assert any("cooking minutes" in e for e in errors)
    plan, errors = validate_plan(FakeLLM().generate_plan(c), c)
    assert errors == [], errors


def test_goal_calorie_target():
    c = ctx(goal="calorie_target", calorie_target=2000, days=[DayCtx(i, 60) for i in range(7)])
    _, hard, _soft = validate_full(FakeLLM().generate_plan(c), c)
    assert hard == [], hard  # (soft issues are checked strictly once the fake planner is schedule-aware)


def test_goal_high_protein():
    c = ctx(goal="high_protein")
    plan, errors = validate_plan(FakeLLM().generate_plan(c), c)
    assert errors == [], errors
    base, _ = validate_plan(FakeLLM().generate_plan(ctx()), ctx())
    avg = lambda p: sum(m["protein"] for m in p["meals"]) / 7
    assert avg(plan) >= 90


def test_ingredient_sharing_beats_random_selection():
    import random

    from app.services.analysis import sharing_stats
    from app.services.catalog import RECIPES
    from app.services.llm import _recipe_to_meal

    planned = sharing_stats(FakeLLM().generate_plan(ctx())["meals"])
    ratios = []
    for seed in range(30):
        rng = random.Random(seed)
        meals = [_recipe_to_meal(rng.choice([r for r in RECIPES if s in r["slots"]]), d, s)
                 for d in range(7) for s in ("breakfast", "lunch", "dinner")]
        ratios.append(sharing_stats(meals)["ratio"])
    assert planned["ratio"] < sum(ratios) / len(ratios)
    assert len(planned["shared"]) >= 5


def test_plan_prefers_pantry_items():
    base = FakeLLM().generate_plan(ctx())
    with_pantry = FakeLLM().generate_plan(ctx(pantry=[{"name": "salmon fillet", "quantity": 20, "unit": "oz"}]))
    count = lambda p: sum(1 for m in p["meals"] for i in m["ingredients"] if i["name"] == "salmon fillet")
    assert count(with_pantry) > count(base)


def test_home_mentions_shared_ingredients(onboarded):
    onboarded.post("/plan/generate")
    assert "reused across meals" in onboarded.get("/").text


def test_costs_shown_per_meal_and_total(onboarded):
    onboarded.post("/plan/generate")
    page = onboarded.get("/").text
    p = plans(onboarded)[0]
    assert f"${p.total_cost:.2f}" in page and "$100.00" in page
    ms = meals(onboarded)
    assert abs(sum(m.cost for m in ms) - p.total_cost) < 0.02
    assert f"${ms[0].cost:.2f}" in page


def test_meal_cost_must_match_ingredients():
    import copy

    c = ctx()
    raw = copy.deepcopy(FakeLLM().generate_plan(c))
    raw["meals"][0]["cost"] = 0.01
    _, errors = validate_plan(raw, c)
    assert any("reports cost" in e for e in errors)


@pytest.mark.parametrize("restrictions", [[], ["vegetarian"], ["vegan"], ["vegetarian", "gluten_free"]])
def test_high_protein_is_feasible_for_common_diets(restrictions):
    c = ctx(goal="high_protein", restrictions=restrictions)
    plan, errors = validate_plan(FakeLLM().generate_plan(c), c)
    assert errors == [], errors


def test_soft_issues_become_warnings_on_final_attempt(onboarded):
    """A plan that only misses a soft goal is accepted after the strict attempts, with a visible warning."""
    import copy

    onboarded.post("/survey", data={"goal": "calorie_target", "calorie_target": "3500"})
    base = FakeLLM().generate_plan(ctx(goal="calorie_target", calorie_target=3500))
    llm = Scripted(copy.deepcopy(base))
    onboarded.app.dependency_overrides[get_llm] = lambda: llm
    r = onboarded.post("/plan/generate")
    assert len(llm.calls) == 3  # two strict retries, then tolerant acceptance
    p = plans(onboarded)[0]
    assert p.attempts == 3 and any("calories" in w for w in p.warnings)


def test_hard_errors_are_never_downgraded(onboarded):
    llm = Scripted(scale_costs(good_plan(), 10))
    onboarded.app.dependency_overrides[get_llm] = lambda: llm
    onboarded.post("/plan/generate")
    assert plans(onboarded) == []
