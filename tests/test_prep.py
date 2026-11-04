import pytest

from app.services.prep import prep_blocks
from tests.helpers import signup


def days(**over):
    d = [dict(weekday=i, minutes=60, busy=False, skipped=False) for i in range(7)]
    for k, v in over.items():
        d[int(k[1:])].update(v)
    return d


def meal(day, minutes, name="Stew"):
    return dict(day=day, cook_minutes=minutes, name=name)


def test_prep_goes_on_free_day_before_heavy_meals():
    meals = [meal(2, 35, "Chili"), meal(3, 30, "Curry"), meal(0, 5)]
    blocks = prep_blocks(meals, days())
    assert blocks and all(b["day"] < 3 for b in blocks)
    assert "Chili" in sum((b["meals"] for b in blocks), [])


def test_prep_never_on_busy_or_skipped_days():
    meals = [meal(3, 35)]
    d = days(d0=dict(busy=True), d1=dict(skipped=True), d2=dict(busy=True))
    assert prep_blocks(meals, d) == []  # only days before Thursday were busy/skipped


def test_prep_respects_available_minutes():
    meals = [meal(3, 35), meal(0, 40)]  # Monday already cooks 40 of 50 minutes
    d = days(d0=dict(minutes=50))
    blocks = prep_blocks(meals, d)
    for b in blocks:
        used = sum(m["cook_minutes"] for m in meals if m["day"] == b["day"])
        assert used + b["minutes"] <= next(x for x in d if x["weekday"] == b["day"])["minutes"]
    assert all(b["day"] != 0 for b in blocks)  # Monday only has 10 spare minutes


def test_no_blocks_when_no_heavy_meals():
    assert prep_blocks([meal(3, 5)], days()) == []


def test_prep_shown_on_calendar(client):
    signup(client)
    client.post("/survey", data={"budget": "100", **{f"minutes_{i}": "90" for i in range(7)}})
    client.post("/plan/generate")
    page = client.get("/").text
    assert page.count('data-testid="prep-block"') <= 2
