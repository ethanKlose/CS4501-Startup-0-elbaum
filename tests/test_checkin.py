import pytest

from app.models import Meal, Plan
from tests.helpers import signup


@pytest.fixture()
def planned(client):
    signup(client)
    client.post("/survey", data={"budget": "100"})
    client.post("/plan/generate")
    return client


def meals(client):
    with client.app.state.session_factory() as s:
        return s.query(Meal).order_by(Meal.id).all()


def test_mark_cooked_and_skipped_persist_and_show_on_calendar(planned):
    ms = meals(planned)
    planned.post(f"/meals/{ms[0].id}/status", data={"status": "cooked"})
    planned.post(f"/meals/{ms[1].id}/status", data={"status": "skipped"})
    after = meals(planned)
    assert (after[0].status, after[1].status, after[2].status) == ("cooked", "skipped", "planned")
    page = planned.get("/").text
    assert 'data-status="cooked"' in page and 'data-status="skipped"' in page
    assert "Mark cooked" in planned.get(f"/meals/{ms[2].id}").text


def test_status_can_be_reset(planned):
    m = meals(planned)[0]
    planned.post(f"/meals/{m.id}/status", data={"status": "cooked"})
    planned.post(f"/meals/{m.id}/status", data={"status": "planned"})
    assert meals(planned)[0].status == "planned"


def test_invalid_status_and_other_users(planned):
    m = meals(planned)[0]
    assert planned.post(f"/meals/{m.id}/status", data={"status": "eaten"}).status_code == 422
    planned.post("/logout")
    signup(planned, "o@o.co")
    assert planned.post(f"/meals/{m.id}/status", data={"status": "cooked"}).status_code == 404


def cook_and_rate(client, meal, rating):
    client.post(f"/meals/{meal.id}/status", data={"status": "cooked"})
    return client.post(f"/meals/{meal.id}/rate", data={"rating": str(rating)}, follow_redirects=False)


def test_rate_only_after_cooked(planned):
    m = meals(planned)[0]
    assert planned.post(f"/meals/{m.id}/rate", data={"rating": "5"}).status_code == 409
    assert cook_and_rate(planned, m, 4).status_code == 303
    assert meals(planned)[0].rating == 4
    assert "Rated 4/5" in planned.get(f"/meals/{m.id}").text


@pytest.mark.parametrize("bad", ["0", "6", "-1"])
def test_rating_range(planned, bad):
    m = meals(planned)[0]
    planned.post(f"/meals/{m.id}/status", data={"status": "cooked"})
    assert planned.post(f"/meals/{m.id}/rate", data={"rating": bad}).status_code == 422


def test_ratings_influence_future_plans(planned):
    from app.services.planner import rating_preferences

    ms = meals(planned)
    hated = ms[2]
    loved = next(m for m in ms if m.name != hated.name)  # distinct recipes, plan content is random
    for m in ms:  # rate every copy of the hated recipe so the average is exact
        if m.name == hated.name and m.id != hated.id:
            cook_and_rate(planned, m, 1)
    cook_and_rate(planned, hated, 1)
    cook_and_rate(planned, loved, 5)
    with planned.app.state.session_factory() as s:
        from app.models import User

        user = s.query(User).first()
        liked, disliked = rating_preferences(s, user)
    assert loved.name in liked and hated.name in disliked
    for _ in range(4):  # across several random regenerations the disliked meal never returns
        planned.post("/plan/regenerate")
        with planned.app.state.session_factory() as s:
            newest = s.query(Plan).order_by(Plan.id.desc()).first().id
            names = [m.name for m in s.query(Meal).filter_by(plan_id=newest)]
        assert hated.name not in names


def test_disliked_validator_rejects():
    from app.services.llm import FakeLLM
    from app.services.validators import validate_plan
    from tests.test_plan import ctx

    c = ctx()
    plan = FakeLLM().generate_plan(c)
    c.disliked = [plan["meals"][0]["name"]]
    _, errors = validate_plan(plan, c)
    assert any("rated poorly" in e for e in errors)


import datetime as dt  # noqa: E402

from app.routers.checkin import checkin_due  # noqa: E402


def test_checkin_due_at_end_of_week():
    plan = Plan(status="ok", created_at=dt.datetime(2026, 11, 2))  # a Monday
    assert not checkin_due(plan, False, now=dt.datetime(2026, 11, 3))  # Tuesday
    assert checkin_due(plan, False, now=dt.datetime(2026, 11, 7))  # Saturday
    assert checkin_due(plan, False, now=dt.datetime(2026, 11, 9))  # 7 days old
    assert not checkin_due(plan, True, now=dt.datetime(2026, 11, 7))  # already done
    assert not checkin_due(None, False)


def last_checkin(client):
    from app.models import CheckIn

    with client.app.state.session_factory() as s:
        return s.query(CheckIn).order_by(CheckIn.id.desc()).first()


def test_checkin_saved_and_summary_shown(planned):
    ms = meals(planned)
    planned.post(f"/meals/{ms[0].id}/status", data={"status": "cooked"})
    planned.post(f"/meals/{ms[1].id}/status", data={"status": "skipped"})
    page = planned.get("/checkin").text
    assert "cooked <strong>1</strong> of 21" in page
    r = planned.post("/checkin", data={"overall": "great", "cook_time": "too_much", "variety": "repetitive", "notes": "no mushrooms"})
    assert "next plan will take this" in r.text
    c = last_checkin(planned)
    assert (c.overall, c.cook_time, c.variety, c.notes) == ("great", "too_much", "repetitive", "no mushrooms")
    planned.post("/checkin", data={"overall": "poor"})  # resubmitting updates, not duplicates
    from app.models import CheckIn

    with planned.app.state.session_factory() as s:
        assert s.query(CheckIn).count() == 1


def test_checkin_invalid_values_are_rejected(planned):
    r = planned.post("/checkin", data={"overall": "???", "cook_time": "x", "variety": "y"})
    assert r.status_code == 422
    assert last_checkin(planned) is None


def test_checkin_responses_shape_next_plan(planned):
    planned.post("/checkin", data={"cook_time": "too_much", "variety": "repetitive", "notes": "no rice, no beans"})
    planned.post("/plan/regenerate")
    with planned.app.state.session_factory() as s:
        plan = s.query(Plan).order_by(Plan.id.desc()).first()
        ms = s.query(Meal).filter_by(plan_id=plan.id).all()
        days = plan.days
    assert all(d["minutes"] <= 33 for d in days)  # 45 * 0.75 -> 30
    for m in ms:  # free-text notes are interpreted into exclusions
        text = " ".join(i["name"] for i in m.ingredients)
        assert "rice" not in text and "beans" not in text


def test_banner_hidden_when_not_due_and_link_exists(planned):
    assert 'data-testid="checkin-banner"' not in planned.get("/").text or dt.datetime.utcnow().weekday() >= 5
    assert 'href="/checkin"' in planned.get("/").text


def pantry_names(client):
    from app.models import PantryItem

    with client.app.state.session_factory() as s:
        return {p.name: p for p in s.query(PantryItem).all()}


def test_unused_ingredients_added_to_pantry_on_checkin(planned):
    ms = meals(planned)
    cooked_only = [m for m in ms if m.day == 0]
    for m in cooked_only:
        planned.post(f"/meals/{m.id}/status", data={"status": "cooked"})
    r = planned.post("/checkin", data={"bought_all": "true"})
    assert 'data-testid="leftovers"' in r.text
    pantry = pantry_names(planned)
    # Whole-package purchases also leave remainders of ingredients cooked on
    # Monday; every saved quantity must equal purchased minus consumed stock.
    from app.services.grocery import build_list
    with planned.app.state.session_factory() as db:
        plan = db.query(Plan).first()
        purchases = (plan.settings or {})['inventory']['purchases']
    consumed = {i['key']: i['quantity'] for i in build_list(m.as_dict() for m in cooked_only)}
    expected = {i['name']: round(i['quantity']-consumed.get(i['key'],0),2)
                for i in purchases if i['quantity']-consumed.get(i['key'],0) > .005}
    assert pantry and {name: item.quantity for name,item in pantry.items()} == pytest.approx(expected, abs=.01)
    assert set(last_checkin(planned).leftovers) == set(pantry)


def test_only_checked_off_items_count_as_bought(planned):
    ms = meals(planned)
    from app.services.grocery import build_list

    items = build_list(m.as_dict() for m in ms)
    bought = items[0]
    planned.post("/grocery/toggle", data={"key": bought["key"], "checked": "true"})
    planned.post("/checkin", data={})
    assert set(pantry_names(planned)) == {bought["name"]}


def test_nothing_unused_if_everything_cooked(planned):
    for m in meals(planned):
        planned.post(f"/meals/{m.id}/status", data={"status": "cooked"})
    r = planned.post("/checkin", data={})
    assert 'data-testid="leftovers"' not in r.text and pantry_names(planned) == {}


def test_leftovers_added_once_and_merge_quantities(planned):
    planned.post("/checkin", data={"bought_all": "true"})
    first = {k: v.quantity for k, v in pantry_names(planned).items()}
    planned.post("/checkin", data={"overall": "great"})  # re-submit must not double-add
    assert {k: v.quantity for k, v in pantry_names(planned).items()} == first


def test_next_plan_prefers_leftovers(planned):
    from app.services.llm import FakeLLM
    from tests.test_plan import ctx

    base = FakeLLM().generate_plan(ctx())
    count = lambda p: sum(1 for m in p["meals"] for i in m["ingredients"] if i["name"] == "salmon fillet")
    left = FakeLLM().generate_plan(ctx(leftovers=["salmon fillet"]))
    assert count(left) > count(base)
    # and the planner wires the latest check-in's leftovers into the context
    planned.post("/checkin", data={"bought_all": "true"})
    with planned.app.state.session_factory() as s:
        from app.models import User
        from app.services import planner

        user = s.query(User).first()
        c = planner.build_context(s, user, FakeLLM(), seed=1)
    assert set(c.leftovers) == set(last_checkin(planned).leftovers) and c.leftovers
