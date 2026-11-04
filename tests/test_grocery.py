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


from app.services.grocery import apply_pantry  # noqa: E402


def base_items():
    return build_list([dict(name="A", ingredients=[ing("rice", 2, "cup", cost=2.0), ing("salt", 1, "tsp"), ing("beans", 1, "can"), ing("onion", 3, "each", "produce", 1.5)])])


def test_pantry_item_without_quantity_is_excluded():
    names = {i["name"] for i in apply_pantry(base_items(), [dict(name="Salt", quantity=None, unit="")])}
    assert "salt" not in names and "rice" in names


def test_fully_covered_quantity_excluded_partial_shows_remainder():
    out = {i["name"]: i for i in apply_pantry(base_items(), [dict(name="rice", quantity=0.5, unit="cup"), dict(name="onion", quantity=5, unit="each")])}
    assert "onion" not in out
    assert out["rice"]["quantity"] == 1.5 and out["rice"]["cost"] == 1.5 and "0.5 cup" in out["rice"]["have"]


def test_different_unit_is_not_subtracted():
    out = {i["name"]: i for i in apply_pantry(base_items(), [dict(name="rice", quantity=2, unit="lb")])}
    assert out["rice"]["quantity"] == 2 and "different unit" in out["rice"]["have"]


def test_plural_matching():
    names = {i["name"] for i in apply_pantry(base_items(), [dict(name="onions", quantity=None, unit="")])}
    assert "onion" not in names


def test_grocery_page_excludes_pantry(client):
    from app.models import Meal

    signup(client)
    client.post("/survey", data={"budget": "100"})
    client.post("/plan/generate")
    with client.app.state.session_factory() as s:
        names = [i["name"] for i in build_list(m.as_dict() for m in s.query(Meal).all())][:3]
    before = client.get("/grocery").text
    assert all(f'data-item="{n}"' in before for n in names)
    for n in names:
        client.post("/pantry/add", data={"name": n})
    after = client.get("/grocery").text
    assert all(f'data-item="{n}"' not in after for n in names)
