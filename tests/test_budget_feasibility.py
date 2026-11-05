import pytest
from app.services.llm import FakeLLM
from app.services.planner import run_with_retries
from app.services.types import PlanContext,DayCtx
from app.services.pricing import plan_checkout
from app.services.validators import validate_full


@pytest.mark.parametrize('seed',[1,2,3])
def test_forty_dollar_week_is_found(seed):
    ctx=PlanContext(budget=40,checkout_budget=True,days=[DayCtx(i,45) for i in range(7)],seed=seed)
    plan,_,warnings=run_with_retries(FakeLLM(),ctx)
    assert not warnings and len(plan['meals'])==21
    assert plan_checkout(plan['meals'],[],{})[0]<=40


def test_budget_fallback_respects_prices_pantry_pins_and_diet():
    from app.services.budget_search import affordable_fallback
    from app.services.catalog import RECIPES
    from app.services.diet import meal_violations
    ctx=PlanContext(budget=50,checkout_budget=True,days=[DayCtx(i,45) for i in range(7)],restrictions=['vegan'],pantry=[{'name':'rice','quantity':8,'unit':'cup'}])
    p=affordable_fallback(ctx,RECIPES);assert p
    ctx.pinned=[p['meals'][0]]
    ctx.price_offers={'rice|cup':dict(name='rice',unit='cup',package_quantity=4,package_price=12,source='Test receipt')}
    p=affordable_fallback(ctx,RECIPES);assert p
    _,hard,_=validate_full(p,ctx);assert not hard
    assert all(not meal_violations(m,['vegan']) for m in p['meals'])
