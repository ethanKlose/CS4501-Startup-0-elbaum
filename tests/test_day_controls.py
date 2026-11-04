import pytest

from app.models import Meal, Plan
from tests.helpers import signup


@pytest.fixture()
def planned(client):
    signup(client)
    client.post("/survey", data={"budget": "100"})
    client.post("/plan/generate")
    return client


def db_meals(client):
    with client.app.state.session_factory() as s:
        return s.query(Meal).all()


def db_plan(client):
    with client.app.state.session_factory() as s:
        return s.query(Plan).order_by(Plan.id.desc()).first()


def test_skip_day_removes_meals_and_updates_total(planned):
    before = db_plan(planned).total_cost
    planned.post("/plan/days/3/skip")
    assert [m for m in db_meals(planned) if m.day == 3] == []
    assert len(db_meals(planned)) == 18
    after = db_plan(planned)
    assert after.total_cost < before
    assert abs(after.total_cost - sum(m.cost for m in db_meals(planned))) < 0.02
    assert "eating out" in planned.get("/").text


def test_restore_day(planned):
    planned.post("/plan/days/3/skip")
    r = planned.post("/plan/days/3/skip")
    assert "Regenerate to fill it" in r.text
    assert not any(d.get("skipped") for d in db_plan(planned).days)


def test_regenerate_keeps_skipped_days(planned):
    planned.post("/plan/days/1/skip")
    planned.post("/plan/generate")
    ms = db_meals(planned)  # old plan's meals were replaced? only the newest plan's meals matter
    plan = db_plan(planned)
    new = [m for m in ms if m.plan_id == plan.id]
    assert len(new) == 18 and all(m.day != 1 for m in new)


def test_skip_requires_plan_and_valid_day(planned):
    assert planned.post("/plan/days/9/skip").status_code == 404


def newest_meals(client):
    plan = db_plan(client)
    return {(m.day, m.slot): m for m in db_meals(client) if m.plan_id == plan.id}


def test_pin_and_unpin(planned):
    m = newest_meals(planned)[(0, "dinner")]
    planned.post(f"/meals/{m.id}/pin")
    assert newest_meals(planned)[(0, "dinner")].pinned is True
    assert "Pinned" in planned.get("/").text
    planned.post(f"/meals/{m.id}/pin")
    assert newest_meals(planned)[(0, "dinner")].pinned is False


def test_pinned_meals_survive_regeneration(planned):
    before = newest_meals(planned)
    keys = [(0, "dinner"), (2, "lunch"), (5, "breakfast")]
    for k in keys:
        planned.post(f"/meals/{before[k].id}/pin")
    for _ in range(3):  # different random seeds each time
        planned.post("/plan/generate")
        after = newest_meals(planned)
        for k in keys:
            assert after[k].name == before[k].name and after[k].ingredients == before[k].ingredients
            assert after[k].pinned
        assert len(after) == 21


def test_unpinned_meals_can_change(planned):
    seen = set()
    for _ in range(4):
        planned.post("/plan/generate")
        seen.add(tuple(m.name for _, m in sorted(newest_meals(planned).items())))
    assert len(seen) > 1


def test_cannot_pin_other_users_meal(planned):
    m = newest_meals(planned)[(0, "dinner")]
    planned.post("/logout")
    signup(planned, "z@z.co")
    assert planned.post(f"/meals/{m.id}/pin").status_code == 404


def test_pin_that_violates_new_restriction_is_dropped(planned):
    m = newest_meals(planned)[(0, "dinner")]
    planned.post(f"/meals/{m.id}/pin")
    planned.post("/survey", data={"restrictions_present": "1", "restrictions": ["vegan", "gluten_free", "dairy_free", "egg_free"]})
    planned.post("/plan/generate")
    assert len(newest_meals(planned)) == 21
