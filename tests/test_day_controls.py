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
