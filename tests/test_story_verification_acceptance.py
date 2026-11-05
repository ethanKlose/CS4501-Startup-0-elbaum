"""Stories #12-#16: validate the actual required slots and shopping budget."""
from app.services.validators import check_budget, check_checkout_budget
from app.services.explain import find_conflicts
from app.services.types import DayCtx,PlanContext
from app.services.llm import _recipe_to_meal
from app.services.catalog import RECIPES


def test_pantried_portions_do_not_spend_the_shopping_budget():
    m=_recipe_to_meal(RECIPES[0],0,'breakfast')
    pantry=[dict(name=i['name'],unit=i['unit'],quantity=10000) for i in m['ingredients']]
    ctx=PlanContext(budget=.01,days=[DayCtx(0,45)],checkout_budget=True,pantry=pantry)
    assert not check_budget({'meals':[m]},ctx)
    assert not check_checkout_budget({'meals':[m]},ctx)
    assert not find_conflicts(ctx)


def test_conflict_estimate_does_not_count_external_or_skipped_slots():
    days=[DayCtx(i,45,skipped=i!=0) for i in range(7)]
    ctx=PlanContext(budget=10,days=days,external_slots=[dict(day=0,slot=s) for s in ('breakfast','lunch')])
    assert not find_conflicts(ctx)


def test_no_breakfast_options_does_not_block_an_external_breakfast():
    names=[r['name'] for r in RECIPES if 'breakfast' in r['slots']]
    ctx=PlanContext(budget=200,days=[DayCtx(0,45)],disliked=names,external_slots=[dict(day=0,slot='breakfast')])
    assert not any('breakfast options' in x for x in find_conflicts(ctx))
