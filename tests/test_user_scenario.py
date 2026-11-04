"""Regression for the reported failure: $200, 2000 cal/day, no cooking on Wed/Thu (via free text).

Meals on Wed/Thu must still exist; they should come from a batch cooked on another day.
"""
import pytest

from app.models import Meal, Plan
from tests.helpers import signup

NOTE = "I can't cook in the middle of the week on Wednesdays and Thursdays"


def test_reported_scenario_generates_a_plan(client):
    signup(client)
    client.post("/survey", data={"budget": "200", "goal": "calorie_target", "calorie_target": "2000", "free_text": NOTE})
    for _ in range(5):  # plans are randomized per click; every one must succeed
        client.post("/plan/generate")
    with client.app.state.session_factory() as s:
        plans = s.query(Plan).order_by(Plan.id).all()
        assert len(plans) == 5, "some generations failed"
        for p in plans:
            meals = s.query(Meal).filter_by(plan_id=p.id).all()
            assert len(meals) == 21
            assert p.total_cost <= 200
            for m in meals:
                if m.day in (2, 3) and m.cook_minutes > 0:  # Wed/Thu: cooked on another day
                    assert m.cook_day != m.day
            avg = sum(m.calories for m in meals) / 7
            assert 1800 <= avg <= 2200
