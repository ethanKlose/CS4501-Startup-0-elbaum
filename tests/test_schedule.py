import random

import pytest

from app.services.catalog import RECIPES
from app.services.llm import _recipe_to_meal
from app.services.schedule import (FREEZER_DAYS, PRE_WEEK, batch_minutes, capacities, freezable, overbook_messages,
                                   schedule, storage_days)
from app.services.types import SLOTS, DayCtx

R = {r["name"]: r for r in RECIPES}


def meal(name, day, slot="dinner"):
    return _recipe_to_meal(R[name], day, slot)


def days(minutes=60, **over):
    d = [DayCtx(i, minutes) for i in range(7)]
    for k, v in over.items():
        d[int(k[1:])].minutes = v
    return d


def random_week(seed):
    rng = random.Random(seed)
    return [_recipe_to_meal(rng.choice([r for r in RECIPES if s in r["slots"]]), d, s) for d in range(7) for s in SLOTS]


# ---- storage rules (conservative, derived from ingredients) ----
def test_storage_rules():
    assert storage_days(meal("Baked salmon with sweet potato", 0)) == 2
    assert storage_days(meal("Garlic shrimp pasta", 0)) == 2
    assert storage_days(meal("Chicken fajitas", 0)) == 4
    assert storage_days(meal("Veggie scramble", 0, "breakfast")) == 1  # fresh
    assert storage_days(meal("Lentil soup", 0)) == 5
    assert storage_days(meal("Greek yogurt parfait", 0, "breakfast")) == 0  # no cooking at all
    assert freezable(meal("Lentil soup", 0)) and not freezable(meal("Chickpea salad bowl", 0))


# ---- capacities ----
def test_capacities_basic_and_prep_days():
    c = capacities(days(45))
    assert c[0] == 45 and c[PRE_WEEK] == 45
    c = capacities(days(45), prep_days=[6], prep_minutes=150)
    assert c[6] == 150 and c[PRE_WEEK] == 150 and c[0] == 45
    assert capacities(days(45), style="daily")[PRE_WEEK] == 0
    d = days(45)
    d[2].skipped = True
    assert capacities(d)[2] == 0


# ---- the reported scenario at the unit level ----
def test_zero_minute_days_are_covered_by_batches_on_other_days():
    ms = [meal("Lentil soup", 2), meal("Chicken and rice bowl", 3), meal("Lentil soup", 3, "lunch")]
    s = schedule(ms, capacities(days(60, d2=0, d3=0)))
    assert not s.overbooked
    for (d, slot), (c, _) in s.assign.items():
        assert c not in (2, 3) and c <= d


def test_same_dish_is_batched_into_one_session():
    ms = [meal("Lentil soup", 1), meal("Lentil soup", 2), meal("Lentil soup", 3)]
    s = schedule(ms, capacities(days(120)))
    assert len(s.sessions) == 1 and s.sessions[0]["servings"] == 3
    assert s.sessions[0]["minutes"] == batch_minutes(30, 3) == 54  # cheaper than 3 x 30


# ---- invariants over many random weeks ----
@pytest.mark.parametrize("seed", range(25))
@pytest.mark.parametrize("style", ["auto", "daily", "sessions", "one_session"])
def test_invariants(seed, style):
    ms = random_week(seed)
    caps = capacities(days(90), style=style, prep_days=[6], prep_minutes=240)
    s = schedule(ms, caps, style=style, prep_days=[6])
    assert s == schedule(ms, caps, style=style, prep_days=[6])  # deterministic
    by = {(m["day"], m["slot"]): m for m in ms}
    assert set(s.assign) == set(by)
    for (d, slot), (c, frozen) in s.assign.items():
        m = by[(d, slot)]
        assert PRE_WEEK <= c <= d
        if m["cook_minutes"] == 0:
            assert c == d
            continue
        window = storage_days(m)
        if frozen:
            assert freezable(m) and window < d - c <= FREEZER_DAYS
        else:
            assert d - c <= window  # never eaten after its fridge life
        if style == "daily":
            assert c == d
    for c, used in s.used.items():
        if c not in s.overbooked:
            assert used <= caps[c]
    assert sum(x["servings"] for x in s.sessions) == sum(1 for m in ms if m["cook_minutes"] > 0)


def test_one_session_uses_a_single_cook_day_when_it_fits():
    ms = [meal(n, d) for d, n in enumerate(["Lentil soup", "Vegetable chili", "Coconut chickpea curry", "Black bean rice bowl",
                                            "Tofu vegetable stir-fry", "Egg fried rice", "Spaghetti marinara"])]
    s = schedule(ms, capacities(days(0), style="one_session", prep_days=[6], prep_minutes=400), style="one_session", prep_days=[6])
    assert {x["cook_day"] for x in s.sessions} == {PRE_WEEK} and not s.overbooked
    assert any(e["frozen"] for x in s.sessions for e in x["eats"])  # late-week dishes go via the freezer


def test_fresh_food_is_not_cooked_days_ahead():
    s = schedule([meal("Veggie scramble", 5, "breakfast")], capacities(days(60)))
    c, frozen = s.assign[(5, "breakfast")]
    assert 5 - c <= 1 and not frozen


def test_fish_not_kept_beyond_two_days_in_fridge():
    s = schedule([meal("Baked salmon with sweet potato", 5)], capacities(days(60, d5=0, d4=0, d3=0), prep_days=[6], prep_minutes=120))
    c, frozen = s.assign[(5, "dinner")]
    assert (5 - c <= 2 and not frozen) or frozen


def test_overbooking_is_reported_not_hidden():
    ms = [meal("Baked salmon with sweet potato", 0), meal("Beef and broccoli stir-fry", 0, "lunch")]
    s = schedule(ms, capacities(days(10)))
    assert s.overbooked and any("cooking minutes but only" in m for m in overbook_messages(s))
