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
