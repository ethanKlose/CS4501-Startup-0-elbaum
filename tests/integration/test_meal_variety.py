"""Per-slot diversity, safe repair and production route checks; no paid provider."""
import copy
import pytest
from app.services.closest_plan import assess,select_plan
from app.services.meal_variety import available_recipes,describe,diversify,nutrition_protected
from app.services.nutrition import catalog_plan
from app.services.llm import FakeLLM
from app.services.types import PlanContext,DayCtx
from app.services.validators import check_diet,check_coverage
from tests.integration.helpers import onboard,generate,snapshot

pytestmark=pytest.mark.integration

@pytest.fixture(autouse=True)
def policy(monkeypatch):monkeypatch.setenv('BEST_EFFORT_PLANNING','1')

def context(**kw):
    values=dict(budget=125,days=[DayCtx(i,45) for i in range(7)],seed=1729,checkout_budget=True)
    values.update(kw);return PlanContext(**values)

def repeated(ctx):
    choices={'breakfast':'Peanut butter banana toast','lunch':'PB&J sandwich','dinner':'Spaghetti marinara'}
    return catalog_plan({'meals':[dict(day=d.weekday,slot=s,name=choices[s]) for d in ctx.active_days() for s in ctx.slots_for(d.weekday)]},ctx)

def test_repeated_seed_is_repaired_per_slot_without_mutating_input():
    ctx=context();raw=repeated(ctx);saved=copy.deepcopy(raw);available=available_recipes(ctx)
    after=diversify(raw,ctx,available,assess);info=assess(after,ctx,available)[3]
    assert raw==saved
    assert info['variety']['penalty']<describe(raw,ctx,available)['penalty']
    for slot,target in [('breakfast',3),('lunch',3),('dinner',4)]:
        assert info['variety']['by_slot'][slot]['distinct']>=target
        assert info['variety']['by_slot'][slot]['max_repeats']<=3
    assert info['shopping']<=ctx.budget*1.05+.001
    assert not assess(after,ctx,available)[1]

def test_screenshot_outside_meals_do_not_disable_diversity_or_safety():
    ctx=context(goal='protein_calorie',protein_target=140,calorie_target=2500,external_slots=[dict(day=d,slot='dinner') for d in (4,5)])
    original=FakeLLM().generate_plan(ctx);old=assess(original,ctx)[3]
    plan,_,warnings=select_plan(FakeLLM(),ctx);report=ctx.closest_metrics
    assert len(plan['meals'])==19 and not check_diet(plan,ctx) and not check_coverage(plan,ctx)
    assert report['variety']['penalty']<old['variety']['penalty']
    assert report['variety']['by_slot']['breakfast']['distinct']>=3
    assert report['variety']['by_slot']['lunch']['distinct']>=3
    assert max(report['variety']['by_slot'][slot]['max_repeats'] for slot in ('breakfast','lunch'))<=4
    assert any('cannot be verified' in warning for warning in warnings)

def test_pins_can_limit_variety_but_are_not_changed():
    ctx=context();raw=repeated(ctx);ctx.pinned=copy.deepcopy([m for m in raw['meals'] if m['slot']=='breakfast'])
    result=diversify(raw,ctx,available_recipes(ctx),assess)
    assert [m for m in result['meals'] if m['slot']=='breakfast']==ctx.pinned
    info=assess(result,ctx)[3]['variety']
    assert info['by_slot']['breakfast']['target']==1
    assert any('adjusted' in note and 'Breakfast' in note for note in info['notices'])

def test_limited_catalog_still_returns_a_complete_plan_with_a_variety_notice():
    ctx=context();raw=repeated(ctx);available=available_recipes(ctx)
    choices={slot:[next(r for r in available[slot] if r['name']==next(m['name'] for m in raw['meals'] if m['slot']==slot))] for slot in available}
    result=diversify(raw,ctx,choices,assess)
    info=assess(result,ctx,choices)
    assert len(result['meals'])==21 and not info[1] and info[3]['variety']['notices']

def test_partial_week_uses_scaled_targets():
    ctx=context(days=[DayCtx(day,45,skipped=day!=0) for day in range(7)])
    raw=repeated(ctx);info=describe(raw,ctx,available_recipes(ctx))
    assert all(row['target']==1 for row in info['by_slot'].values())
    assert info['penalty']==0 and len(diversify(raw,ctx,available_recipes(ctx),assess)['meals'])==3

def test_nutrition_guard_allows_small_tradeoffs_but_blocks_large_shortfalls():
    ctx=context(goal='protein_calorie',protein_target=140,calorie_target=2000)
    old={'meals':[dict(day=0,calories=c,protein=p) for c,p in [(650,45),(650,45),(700,50)]]}
    acceptable=copy.deepcopy(old);acceptable['meals'][0].update(calories=600,protein=40)
    poor=copy.deepcopy(old);poor['meals'][0].update(calories=300,protein=10)
    assert nutrition_protected(acceptable,old,ctx)
    assert not nutrition_protected(poor,old,ctx)

def test_dietary_restrictions_are_preserved_during_diversification():
    ctx=context(restrictions=['vegan','gluten_free'],excluded=['sesame'])
    plan,_,_=select_plan(FakeLLM(),ctx)
    assert len(plan['meals'])==21 and not check_diet(plan,ctx)

def test_tight_budget_still_produces_a_plan_instead_of_failing_variety():
    ctx=context(budget=30)
    plan,_,warnings=select_plan(FakeLLM(),ctx)
    assert len(plan['meals'])==21 and not assess(plan,ctx)[1]
    assert warnings  # Closest plan states any remaining budget/variety differences.

def test_repair_does_not_add_provider_calls():
    ctx=context()
    class Provider:
        name='controlled'
        calls=0
        def generate_plan(self,context,feedback):self.calls+=1;return repeated(context)
    provider=Provider();plan,_,_=select_plan(provider,ctx)
    assert provider.calls==1 and len(plan['meals'])==21
    assert ctx.closest_metrics['variety']['by_slot']['breakfast']['distinct']>=3

def test_calendar_renders_per_slot_variety_and_plan_checks(application,web):
    onboard(web);page=generate(web);saved=snapshot(application)
    assert 'data-testid="meal-variety-summary"' in page.text
    assert 'Meal variety' in page.text
    assert set(saved['settings']['closest']['variety']['by_slot'])=={'breakfast','lunch','dinner'}


def test_repetition_counts_across_lunch_and_dinner_together():
    ctx=context();raw=repeated(ctx)
    for meal in raw['meals']:
        if meal['slot'] in ('lunch','dinner'):meal['name']='Lentil and tofu power bowl'
    raw=catalog_plan(raw,ctx)
    report=describe(raw,ctx,available_recipes(ctx))
    assert report['max_repeats']==14 and report['global_penalty']>0
    assert any('across meal types' in warning for warning in report['notices'])
