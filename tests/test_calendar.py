import pytest

from app.models import Meal
from tests.helpers import signup


@pytest.fixture()
def planned(client):
    signup(client)
    client.post("/survey", data={"budget": "100"})
    client.post("/plan/generate")
    return client


def test_calendar_shows_all_seven_days_and_their_meals(planned):
    page = planned.get("/").text
    for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        assert f">{day}</h2>" in page
    assert page.count('class="meal"') == 21
    with planned.app.state.session_factory() as s:
        for m in s.query(Meal).all():
            assert m.name.replace("&", "&amp;") in page or m.name in page


def test_calendar_is_responsive(planned):
    css = planned.get("/static/style.css").text
    assert "@media (max-width: 520px)" in css and 'name="viewport"' in planned.get("/").text


def first_meal(client):
    with client.app.state.session_factory() as s:
        return s.query(Meal).first()


def test_meal_detail_shows_recipe_time_ingredients(planned):
    m = first_meal(planned)
    assert f'href="/meals/{m.id}"' in planned.get("/").text
    page = planned.get(f"/meals/{m.id}").text
    assert f"{m.cook_minutes} min" in page
    assert m.ingredients[0]["name"] in page
    assert m.steps[0].replace("&", "&amp;") in page or m.steps[0] in page
    assert 'href="/"' in page  # close/back link returns to the calendar


def test_meal_detail_is_private(planned):
    m = first_meal(planned)
    planned.post("/logout")
    signup(planned, "other@x.co")
    assert planned.get(f"/meals/{m.id}").status_code == 404
    assert planned.get("/meals/99999").status_code == 404
