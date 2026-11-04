import pytest

from app.services.grocery import build_list
from tests.helpers import signup


def ing(name, q, unit="", section="pantry", cost=1.0):
    return dict(name=name, quantity=q, unit=unit, section=section, cost=cost)


def test_duplicates_are_merged_with_combined_quantities():
    meals = [dict(name="A", ingredients=[ing("Rice", 0.75, "cup"), ing("onion", 1, "each", "produce")]),
             dict(name="B", ingredients=[ing("rice", 0.5, "cup"), ing("rice", 1, "lb")])]
    items = {(i["name"], i["unit"]): i for i in build_list(meals)}
    assert items[("rice", "cup")]["quantity"] == 1.25 and items[("rice", "cup")]["cost"] == 2.0
    assert ("rice", "lb") in items  # different unit stays separate
    assert items[("rice", "cup")]["meals"] == ["A", "B"]


def test_one_list_for_whole_plan(client):
    signup(client)
    client.post("/survey", data={"budget": "100"})
    assert "Generate a plan first" in client.get("/grocery").text
    client.post("/plan/generate")
    page = client.get("/grocery").text
    from app.models import Meal

    with client.app.state.session_factory() as s:
        meals = [m.as_dict() for m in s.query(Meal).all()]
    items = build_list(meals)
    assert len(items) < sum(len(m["ingredients"]) for m in meals)  # consolidation happened
    assert page.count("<li data-item=") == len(items)


def test_grocery_requires_login(client):
    assert client.get("/grocery", follow_redirects=False).status_code == 303
