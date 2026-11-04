from app.models import Plan
from app.services import planner
from app.services.lifestyle import violations
from app.services.types import PlanContext,DayCtx
from tests.helpers import signup


def test_kitchen_rules_are_hard_constraints():
    ctx=PlanContext(budget=100,days=[DayCtx(i,45) for i in range(7)],equipment=['microwave'],cooking_skill='beginner')
    assert violations(dict(name='Baked chicken',steps=['Roast in oven'],cook_minutes=40),ctx)
    assert not violations(dict(name='Hummus wrap',steps=['Spread and roll'],cook_minutes=0),ctx)


def test_external_meal_is_not_generated_or_shopped(client):
    signup(client);client.post('/survey',data={'budget':'150'})
    client.post('/preferences/lifestyle',data={'equipment':['stove','oven','fridge','freezer','toaster','blender'],'external_2_lunch':'on'})
    client.post('/plan/generate')
    with client.app.state.session_factory() as s:
        p=s.query(Plan).first()
        assert p and len(p.meals)==20
        assert not any(m.day==2 and m.slot=='lunch' for m in p.meals)
