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
    loved = ms[5]
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
