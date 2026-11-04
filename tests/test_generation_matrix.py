"""Generation must be flexible: realistic setups never hard-fail, and the common ones are warning-free."""
import itertools

import pytest

from app.services.llm import FakeLLM
from app.services.types import DayCtx, PlanContext
from app.services.validators import validate_full

RESTRICTIONS = [[], ["vegetarian"], ["vegan"], ["gluten_free"], ["dairy_free", "nut_allergy"], ["vegan", "gluten_free"]]
SCHEDULES = {"default": {}, "no_cook_wed_thu": {2: 0, 3: 0}}
GOALS = [("none", None), ("high_protein", None), ("calorie_target", 1800), ("calorie_target", 2000)]


def make(restrictions, schedule, goal, cal, seed, budget=200):
    days = [DayCtx(i, SCHEDULES[schedule].get(i, 45)) for i in range(7)]
    return PlanContext(budget=budget, days=days, restrictions=restrictions, goal=goal, calorie_target=cal, seed=seed)


@pytest.mark.parametrize("restrictions,schedule,goal", [(r, s, g) for r, s, g in itertools.product(RESTRICTIONS, SCHEDULES, GOALS)])
def test_no_hard_failures_for_realistic_setups(restrictions, schedule, goal):
    g, cal = goal
    c = make(restrictions, schedule, g, cal, seed=3)
    plan, hard, soft = validate_full(FakeLLM().generate_plan(c), c)
    assert hard == [], hard
    assert len(plan["meals"]) == 21


@pytest.mark.parametrize("restrictions", RESTRICTIONS)
def test_default_schedule_is_warning_free(restrictions):
    for seed in (1, 2):
        c = make(restrictions, "default", "calorie_target", 2000, seed)
        _, hard, soft = validate_full(FakeLLM().generate_plan(c), c)
        assert hard == [] and soft == [], (hard, soft)


@pytest.mark.parametrize("restrictions", [[], ["vegetarian"], ["gluten_free"], ["vegan"]])
def test_no_cook_midweek_is_warning_free(restrictions):
    for seed in (1, 2):
        c = make(restrictions, "no_cook_wed_thu", "calorie_target", 2000, seed)
        _, hard, soft = validate_full(FakeLLM().generate_plan(c), c)
        assert hard == [] and soft == [], (hard, soft)


def test_no_cooking_on_zero_minute_days():
    from app.services.validators import schedule_for

    c = make([], "no_cook_wed_thu", "none", None, 1)
    plan, _, _ = validate_full(FakeLLM().generate_plan(c), c)
    s = schedule_for(plan, c)
    assert all(cook_day not in (2, 3) for cook_day, _ in s.assign.values() if cook_day != -9) or all(
        m["cook_minutes"] == 0 for m in plan["meals"] if s.assign[(m["day"], m["slot"])][0] in (2, 3))


def test_reported_scenario_is_reliable_across_many_random_seeds():
    """$200, 2000 cal, no cooking Wed/Thu: every random draw must be a clean, on-target plan (was ~3% flaky)."""
    for seed in range(1, 41):
        c = make([], "no_cook_wed_thu", "calorie_target", 2000, seed)
        plan, hard, soft = validate_full(FakeLLM().generate_plan(c), c)
        avg = sum(m["calories"] for m in plan["meals"]) / 7
        assert hard == [] and soft == [] and 1800 <= avg <= 2200, (seed, round(avg), hard, soft)
