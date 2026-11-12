"""#22: regenerated plans get exactly the same verification as the first plan."""
import copy

import pytest

from app.models import Meal, Plan
from app.services.llm import FakeLLM, get_llm
from tests.helpers import signup
from tests.test_plan import Scripted, ctx, scale_costs, good_plan


@pytest.fixture()
def planned(client):
    signup(client)
    client.post("/survey", data={"budget": "100"})
    client.post("/plan/generate")
    return client


def plan_ids(client):
    with client.app.state.session_factory() as s:
        return [p.id for p in s.query(Plan).order_by(Plan.id)]


def test_regenerate_over_budget_is_retried_then_accepted(planned):
    good = good_plan()
    llm = Scripted(scale_costs(good, 10), good)
    planned.app.dependency_overrides[get_llm] = lambda: llm
    planned.post("/plan/regenerate")
    assert len(llm.calls) == 2 and "exceeds the weekly budget" in llm.calls[1][0]
    assert len(plan_ids(planned)) == 2


def test_regenerate_never_saves_invalid_plan_and_shows_same_message(planned):
    llm = Scripted(scale_costs(FakeLLM().generate_plan(ctx()), 10))
    planned.app.dependency_overrides[get_llm] = lambda: llm
    r = planned.post("/plan/regenerate")
    assert len(plan_ids(planned)) == 1  # still only the original
    assert "exceeds the weekly budget" in r.text  # same explanation path as first generation


def test_regenerate_dropping_a_pinned_meal_is_rejected(planned):
    with planned.app.state.session_factory() as s:
        meal = s.query(Meal).filter_by(day=1, slot="dinner").first()
        mid = meal.id
    planned.post(f"/meals/{mid}/pin")
    tampered = FakeLLM().generate_plan(ctx(seed=99))
    for m in tampered["meals"]:
        if (m["day"], m["slot"]) == (1, "dinner"):
            m["name"] = "Totally different dinner"
            m["ingredients"] = m["ingredients"][:1]
            m["cost"] = round(sum(i["cost"] for i in m["ingredients"]), 2)
    llm = Scripted(tampered)
    planned.app.dependency_overrides[get_llm] = lambda: llm
    planned.post("/plan/regenerate")
    assert len(plan_ids(planned)) == 1
    assert any("Pinned meal" in e for e in llm.calls[1])


def test_regenerate_respects_new_diet_restriction(planned):
    planned.post("/survey", data={"restrictions_present": "1", "restrictions": ["vegetarian"]})
    unrestricted = FakeLLM().generate_plan(ctx())
    unrestricted["meals"][0]["ingredients"].append(dict(name="beef sirloin", quantity=4, unit="oz", section="meat", cost=1.0))
    unrestricted["meals"][0]["cost"] = round(unrestricted["meals"][0]["cost"] + 1.0, 2)
    llm = Scripted(unrestricted)
    planned.app.dependency_overrides[get_llm] = lambda: llm
    planned.post("/plan/regenerate")
    assert len(plan_ids(planned)) == 1 and any("vegetarian" in e for e in llm.calls[1])


@pytest.mark.parametrize('field', ['quantity', 'calories', 'steps', 'cook_minutes', 'unit', 'protein'])
def test_regenerate_cannot_mutate_pinned_recipe(planned, field):
    with planned.app.state.session_factory() as s:
        old = s.query(Plan).first()
        meal = s.query(Meal).filter_by(plan_id=old.id, day=0, slot='breakfast').first()
        mid, old_plan_id = meal.id, old.id
    planned.post(f'/meals/{mid}/pin')

    class Tampered:
        calls = 0
        def interpret_preferences(self, text):
            return {'excluded': [], 'day_minutes_cap': {}}
        def generate_plan(self, context, feedback=()):
            self.calls += 1
            raw = copy.deepcopy(FakeLLM().generate_plan(context))
            pinned = context.pinned[0]
            target = next(m for m in raw['meals'] if (m['day'], m['slot']) == (pinned['day'], pinned['slot']))
            if field == 'quantity': target['ingredients'][0]['quantity'] *= 10
            elif field == 'unit': target['ingredients'][0]['unit'] = 'lb'
            elif field == 'steps': target['steps'] = ['Changed instructions.']
            else: target[field] += 1
            return raw

    llm = Tampered()
    planned.app.dependency_overrides[get_llm] = lambda: llm
    result = planned.post('/plan/regenerate')
    assert llm.calls == 3
    assert plan_ids(planned) == [old_plan_id]
    assert 'Pinned meal' in result.text
