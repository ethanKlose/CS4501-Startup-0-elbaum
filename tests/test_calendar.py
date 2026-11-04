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
    assert page.count('data-status="') == 21
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


def test_cooking_plan_lists_every_session_and_labels_batched_meals(planned):
    page = planned.get("/").text
    assert 'data-testid="cook-plan"' in page and "Cooking plan" in page
    with planned.app.state.session_factory() as s:
        ms = s.query(Meal).all()
    cooked = [m for m in ms if m.cook_minutes > 0]
    assert cooked
    for name in {m.name for m in cooked}:
        assert name.replace("&", "&amp;") in page
    batched = [m for m in cooked if m.cook_day != m.day]
    if batched:
        assert "batch" in page


def test_meal_page_says_when_it_is_cooked(planned):
    with planned.app.state.session_factory() as s:
        m = next(x for x in s.query(Meal).all() if x.cook_minutes > 0)
    page = planned.get(f"/meals/{m.id}").text
    assert 'data-testid="cook-when"' in page and ("Cook this fresh" in page or "Cooked ahead" in page)


def test_plan_warnings_are_shown(planned):
    from app.models import Plan

    with planned.app.state.session_factory() as s:
        p = s.query(Plan).first()
        p.warnings = ["Wednesday has 1250 calories; the target is 2000."]
        s.commit()
    page = planned.get("/").text
    assert 'data-testid="plan-warnings"' in page and "Heads up" in page and "Wednesday has 1250" in page


def test_batch_cooking_covers_a_no_cook_day(client):
    signup(client)
    client.post("/survey", data={"budget": "150", "minutes_2": "0", "minutes_3": "0", **{f"minutes_{i}": "60" for i in (0, 1, 4, 5, 6)}})
    client.post("/plan/generate")
    with client.app.state.session_factory() as s:
        ms = s.query(Meal).all()
    assert len(ms) == 21
    assert all(m.cook_day not in (2, 3) for m in ms if m.cook_minutes > 0)
    assert any(m.day in (2, 3) and m.cook_minutes > 0 and m.cook_day < m.day for m in ms) or all(
        m.cook_minutes == 0 for m in ms if m.day in (2, 3))
