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


def names(client):
    return tuple(m.name for _, m in sorted(newest_meals(client).items()))


def test_one_click_regenerate_uses_saved_survey(planned):
    first = names(planned)
    assert 'action="/plan/regenerate"' in planned.get("/").text
    seen = {first}
    for _ in range(4):
        r = planned.post("/plan/regenerate")  # no form data: everything comes from saved answers
        assert r.status_code == 200
        seen.add(names(planned))
    assert len(seen) > 1
    assert db_plan(planned).total_cost <= 100


def test_saved_survey_edits_apply_to_next_regeneration(planned):
    planned.post("/survey", data={"restrictions_present": "1", "restrictions": ["vegan"]})
    planned.post("/plan/regenerate")
    from app.services.diet import meal_violations

    for m in newest_meals(planned).values():
        assert meal_violations(m.as_dict(), ["vegan"]) == []


def test_failed_regeneration_keeps_previous_valid_plan(planned):
    old = db_plan(planned).id
    from tests.helpers import set_budget

    set_budget(planned, 5)
    r = planned.post("/plan/regenerate")
    assert "too low" in r.text
    assert db_plan(planned).id == old


def test_swap_changes_only_one_meal(planned):
    before = newest_meals(planned)
    target = before[(2, "dinner")]
    planned.post(f"/meals/{target.id}/swap")
    after = newest_meals(planned)
    assert after[(2, "dinner")].name != target.name
    for k, m in before.items():
        if k != (2, "dinner"):
            assert after[k].name == m.name and after[k].ingredients == m.ingredients
    assert len(after) == 21


def test_swap_updates_cost_and_stays_in_budget(planned):
    target = newest_meals(planned)[(0, "dinner")]
    planned.post(f"/meals/{target.id}/swap")
    plan = db_plan(planned)
    ms = list(newest_meals(planned).values())
    assert abs(plan.total_cost - sum(m.cost for m in ms)) < 0.02
    assert plan.total_cost <= 100


def test_swap_is_verified_and_failure_leaves_meal_unchanged(planned):
    from app.services.llm import FakeLLM, get_llm
    from tests.test_plan import Scripted, ctx

    target = newest_meals(planned)[(1, "lunch")]
    bad = FakeLLM().generate_plan(ctx())
    for m in bad["meals"]:
        if (m["day"], m["slot"]) == (1, "lunch"):
            m["ingredients"].append(dict(name="beef sirloin", quantity=50, unit="oz", section="meat", cost=500))
            m["cost"] = round(sum(i["cost"] for i in m["ingredients"]), 2)
    planned.app.dependency_overrides[get_llm] = lambda: Scripted(bad)
    r = planned.post(f"/meals/{target.id}/swap")
    assert "swap that meal" in r.text
    assert newest_meals(planned)[(1, "lunch")].name == target.name


def test_cannot_swap_other_users_meal(planned):
    target = newest_meals(planned)[(1, "lunch")]
    planned.post("/logout")
    signup(planned, "q@q.co")
    assert planned.post(f"/meals/{target.id}/swap").status_code == 404


def test_cook_days_are_saved_and_never_after_eating(planned):
    for m in newest_meals(planned).values():
        assert -1 <= m.cook_day <= m.day
        if m.cook_minutes == 0:
            assert m.cook_day == m.day


def test_skipping_and_swapping_reschedule_cooking(planned):
    planned.post("/plan/days/0/skip")
    assert all(m.day != 0 for m in newest_meals(planned).values())
    for m in newest_meals(planned).values():
        assert -1 <= m.cook_day <= m.day
    target = newest_meals(planned)[(4, "dinner")]
    planned.post(f"/meals/{target.id}/swap")
    for m in newest_meals(planned).values():
        assert -1 <= m.cook_day <= m.day


@pytest.mark.parametrize('status,rating', [('cooked', None), ('cooked', 5), ('skipped', None), ('planned', 5)])
def test_swap_preserves_completed_and_rated_history(planned, status, rating):
    target = newest_meals(planned)[(0, 'dinner')]
    with planned.app.state.session_factory() as s:
        m = s.get(Meal, target.id)
        m.status, m.rating = status, rating
        s.commit()
    response = planned.post(f'/meals/{target.id}/swap')
    assert 'Only planned, unrated meals can be swapped' in response.text
    after = newest_meals(planned)[(0, 'dinner')]
    assert (after.name, after.status, after.rating) == (target.name, status, rating)
    assert f'action="/meals/{target.id}/swap"' not in planned.get(f'/meals/{target.id}').text
