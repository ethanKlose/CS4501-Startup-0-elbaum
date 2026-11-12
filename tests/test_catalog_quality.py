import copy
from collections import Counter
import pytest
from app.services.catalog import RECIPES
from app.services.nutrition import INGREDIENTS,calculate,evidence,catalog_plan
from app.services.pricing import reference_offers,apply_recipe_prices
from app.services.diet import meal_violations,term_hits
from app.services.planning_quality import candidate_pool,eligible_recipes,improve_plan,metrics
from app.services.schema import MealIn
from app.services.types import PlanContext,DayCtx
from app.services.validators import validate_full


def context(**kwargs):
    values=dict(budget=100,days=[DayCtx(i,45) for i in range(7)],checkout_budget=True,seed=23)
    values.update(kwargs);return PlanContext(**values)


def cheap_plan(ctx):
    choices={'breakfast':'Peanut butter banana toast','lunch':'PB&J sandwich','dinner':'Spaghetti marinara'}
    return catalog_plan({'meals':[dict(day=d.weekday,slot=slot,name=choices[slot]) for d in ctx.active_days() for slot in ctx.slots_for(d.weekday)]},ctx)


def test_expansion_is_used_by_real_recipes_and_every_unit_has_sourced_nutrients_and_a_price():
    assert len(RECIPES)>=110 and len(INGREDIENTS)>=118
    assert len({r['name'] for r in RECIPES})==len(RECIPES)
    used=set();offers=reference_offers()
    for recipe in RECIPES:
        assert recipe['slots'] and set(recipe['slots'])<=set(['breakfast','lunch','dinner'])
        MealIn.model_validate(dict(recipe,day=0,slot=recipe['slots'][0]))
        assert calculate(recipe['ingredients'])==(recipe['calories'],recipe['protein'])
        assert evidence(recipe)
        for item in recipe['ingredients']:
            record=INGREDIENTS[item['name']];used.add(item['name'])
            assert record['fdc_id']>0 and record['source_url'].startswith('https://fdc.nal.usda.gov/food-details/')
            assert record['grams_per_unit'][item['unit']]>0
            assert offers[item['name']+'|'+item['unit']]['package_quantity']>0
    assert used==set(INGREDIENTS)


@pytest.mark.parametrize('ingredient,restriction',[('mackerel','vegetarian'),('sockeye salmon','vegan'),('pork tenderloin','halal'),('bulgur','gluten_free'),('pearl barley','gluten_free'),('walnuts','nut_allergy'),('tahini','sesame_allergy'),('hummus','sesame_allergy'),('sesame seeds','sesame_allergy')])
def test_expanded_ingredient_diet_rules(ingredient,restriction):
    meal=dict(name='Test meal',ingredients=[dict(name=ingredient)])
    assert meal_violations(meal,[restriction])


def test_ingredient_exceptions_do_not_hide_other_allergens_or_gluten():
    assert term_hits('corn tortilla','gluten_free')==[]
    assert term_hits('corn tortilla with wheat flour','gluten_free')
    assert term_hits('almond milk','nut_allergy') and not term_hits('almond milk','dairy_free')
    assert term_hits('edamame','soy') and term_hits('tahini','sesame')


def test_explicit_package_prices_do_not_change_when_recipes_are_added_or_callers_modify_a_copy():
    original=reference_offers()
    RECIPES.append(dict(name='temporary test',ingredients=[dict(name='rice',unit='cup',quantity=1,cost=999)]))
    try:assert reference_offers()==original
    finally:RECIPES.pop()
    copied=reference_offers();copied['rice|cup']['package_price']=999
    assert reference_offers()==original
    updated=apply_recipe_prices(RECIPES[0],{'rolled oats|cup':dict(package_quantity=4,package_price=8)})
    assert next(i['cost'] for i in updated['ingredients'] if i['name']=='rolled oats')==1


def test_budget_retry_retains_variety_and_filters_hard_preferences_before_provider_calls():
    ctx=context(restrictions=['vegan','gluten_free'],excluded=['sesame'])
    pool=candidate_pool(ctx,eligible_recipes(ctx,RECIPES),retry_budget=True,per_slot=14)
    assert all(2<len(options)<=14 for options in pool.values())
    assert all(not meal_violations(recipe,ctx.restrictions,ctx.excluded) for options in pool.values() for recipe in options)
    again=candidate_pool(ctx,eligible_recipes(ctx,RECIPES),retry_budget=True,per_slot=14)
    assert [[r['name'] for r in values] for values in pool.values()]==[[r['name'] for r in values] for values in again.values()]


def test_valid_cheap_proposal_gets_more_variety_under_actual_checkout_budget_without_a_model_call():
    ctx=context();before=cheap_plan(ctx);saved=copy.deepcopy(before);old=metrics(before,ctx)
    result=improve_plan(before,ctx,RECIPES);new=metrics(result,ctx)
    assert before==saved
    assert new['recipes']>=8 and new['ingredients']>old['ingredients']
    assert new['max_repeats']<old['max_repeats']
    assert new['checkout']<=ctx.budget and new['checkout']>old['checkout']
    assert validate_full(result,ctx)[1]==[] and ctx.quality_metrics['evaluated']<=420


def test_optimizer_preserves_pins_and_never_repairs_an_invalid_provider_proposal():
    ctx=context();plan=cheap_plan(ctx);ctx.pinned=[copy.deepcopy(plan['meals'][0])]
    result=improve_plan(plan,ctx,RECIPES)
    first=next(m for m in result['meals'] if (m['day'],m['slot'])==(0,'breakfast'))
    assert first==MealIn.model_validate(ctx.pinned[0]).model_dump()
    bad=copy.deepcopy(plan);bad['meals'].pop()
    assert improve_plan(bad,ctx,RECIPES)==bad


def test_full_pantry_is_allowed_to_make_checkout_free_without_a_minimum_spend_failure():
    ctx=context(pantry=[dict(name=name,quantity=None,unit='') for name in INGREDIENTS]);plan=cheap_plan(ctx)
    result=improve_plan(plan,ctx,RECIPES)
    assert metrics(result,ctx)['checkout']==0
    assert not ctx.quality_metrics['preferred_range_applies']
    assert validate_full(result,ctx)[1:]==([],[])


def test_partial_week_does_not_force_a_full_week_of_spending():
    ctx=context(days=[DayCtx(day,45,skipped=day!=0) for day in range(7)])
    result=improve_plan(cheap_plan(ctx),ctx,RECIPES)
    assert len(result['meals'])==3 and not ctx.quality_metrics['preferred_range_applies']
    assert validate_full(result,ctx)[1]==[]


def test_provider_payload_uses_local_prices_and_package_context_without_full_recipes():
    from app.services.llm import AnthropicLLM
    from app.services.pricing import plan_checkout
    import json
    ctx=context(price_offers={'rolled oats|cup':dict(package_quantity=4,package_price=8,source='Test receipt')})
    captured=[]
    llm=AnthropicLLM.__new__(AnthropicLLM)
    def ask(system,user,max_tokens):
        captured.append((system,json.loads(user)))
        return {'meals':[]}
    llm._ask=ask
    llm.generate_plan(ctx,['Whole-package budget exceeded'])
    system,payload=captured[0]
    assert 'do not minimize spending' in system
    assert 'Size portions up' not in system
    approved=payload['approved_recipes']
    oats=next(row for row in approved if row['name']=='Overnight oats with banana')
    canonical=next(recipe for recipe in RECIPES if recipe['name']==oats['name'])
    priced=apply_recipe_prices(canonical,ctx.price_offers)
    assert oats['cost']==priced['cost']
    assert oats['shopping_cost_once']==plan_checkout([priced],ctx.pantry,ctx.price_offers)[0]
    assert oats['ingredients']==[i['name'] for i in priced['ingredients']]
    assert 'steps' not in oats and all(isinstance(name,str) for name in oats['ingredients'])
    assert all(len(names)>2 for names in payload['approved_names_by_slot'].values())
    assert len(captured)==3  # one initial response and two bounded missing-slot repairs


def test_regeneration_shortlists_explore_other_foods_without_changing_seed_reproducibility():
    first=context(seed=1);second=context(seed=23)
    a=candidate_pool(first,eligible_recipes(first,RECIPES))
    b=candidate_pool(second,eligible_recipes(second,RECIPES))
    assert {r['name'] for values in a.values() for r in values}!={r['name'] for values in b.values() for r in values}
    assert candidate_pool(first,eligible_recipes(first,RECIPES))==a


def test_one_slot_swap_searches_beyond_the_general_shortlist_and_preserves_other_meals(monkeypatch):
    from app.services.budget_search import affordable_fallback
    ctx=context();old=cheap_plan(ctx);target=old['meals'][-1]
    ctx.pinned=copy.deepcopy(old['meals'][:-1]);ctx.disliked=[target['name']]
    def unavailable_shortlist(*args,**kwargs):
        raise AssertionError('A one-slot search must inspect all eligible replacements')
    monkeypatch.setattr('app.services.planning_quality.candidate_pool',unavailable_shortlist)
    result=affordable_fallback(ctx,RECIPES)
    assert result is not None and validate_full(result,ctx)[1]==[]
    assert next(m for m in result['meals'] if (m['day'],m['slot'])==(target['day'],target['slot']))['name']!=target['name']
    assert all(m==MealIn.model_validate(p).model_dump() for m,p in zip(result['meals'][:-1],ctx.pinned))
