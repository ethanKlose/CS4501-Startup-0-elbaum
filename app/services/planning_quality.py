"""Bounded, provider-independent plan improvement using real package estimates.

Budget is a ceiling. Variety, user targets, pantry use and manageable prep are the
objective; preferred spending is a weak tie-breaker, never a minimum-spend rule.
"""
import copy
import math
import random
from collections import Counter, defaultdict

from app.services.diet import meal_violations
from app.services.lifestyle import violations
from app.services.nutrition_goals import protein_target
from app.services.pricing import apply_recipe_prices, plan_checkout


def eligible_recipes(ctx, recipes):
    return [apply_recipe_prices(recipe, ctx.price_offers) for recipe in recipes
            if not meal_violations(recipe, ctx.restrictions, ctx.excluded)
            and not violations(recipe, ctx) and recipe['name'] not in ctx.disliked]


def variety_target(ctx):
    slots=sum(len(ctx.slots_for(day.weekday)) for day in ctx.active_days())
    return min(slots, max(3, math.ceil(min(14, 6 + ctx.budget / 18) * slots / 21)))


def candidate_pool(ctx, recipes, retry_budget=False, per_slot=18):
    """A small balanced shortlist, including inexpensive and nutrient-fit choices.

    Seeded ordering lets regeneration explore the expanded catalog. Even after a
    budget miss we retain nutrient-fit alternatives, rather than only two foods.
    """
    from app.services.types import SLOTS
    rng=random.Random(ctx.seed)
    result={}
    target=ctx.calorie_target or 2000
    pro=protein_target(ctx)
    leftovers={name.lower() for name in ctx.leftovers}
    pantry={item['name'].lower() for item in ctx.pantry}
    def stock_fit(recipe):
        names={item['name'].lower() for item in recipe['ingredients']}
        return len(names & leftovers)+.4*len(names & pantry)
    for slot in SLOTS:
        options=[r for r in recipes if slot in r['slots']]
        jitter={r['name']:rng.random() for r in options}
        def fit(r):
            return (abs(r['calories']-target/3)/max(target/3,1)
                    + (max(0,pro/3-r['protein'])/max(pro/3,1) if pro else 0)
                    + .15*(r['name'] in ctx.avoid)-.15*(r['name'] in ctx.liked)-.6*stock_fit(r)+.15*jitter[r['name']])
        cheap=sorted(options,key=lambda r:(r['cost'],fit(r)))
        fitted=sorted(options,key=fit)
        fresh=sorted(options,key=lambda r:jitter[r['name']])
        richer=sorted(options,key=lambda r:(-r['cost'],fit(r)))
        dense=sorted(options,key=lambda r:(r['cost']/max(r['calories'],1),fit(r)))
        selected={}
        groups=[cheap[:6 if retry_budget else 3],fitted[:7],dense[:2] if retry_budget else [],fresh[:5],richer[:3]]
        for group in groups:
            for recipe in group:
                selected.setdefault(recipe['name'],recipe)
        # Keep the shortlist bounded without consistently losing the expensive end.
        names=list(selected)
        if len(names)>per_slot:
            mandatory=list(dict.fromkeys(r['name'] for r in fitted[:4]+cheap[:6 if retry_budget else 3]+(dense[:2] if retry_budget else [])+richer[:2]))
            names=list(mandatory)+[name for name in names if name not in mandatory][:per_slot-len(mandatory)]
        rng.shuffle(names)
        result[slot]=[selected[name] for name in names]
    return result


def metrics(plan, ctx):
    meals=plan['meals'];counts=Counter(m['name'] for m in meals)
    checkout,rows=plan_checkout(meals,ctx.pantry,ctx.price_offers)
    daily=defaultdict(lambda:{'calories':0,'protein':0.0})
    produce=set();ingredients=set()
    for meal in meals:
        daily[meal['day']]['calories']+=meal['calories'];daily[meal['day']]['protein']+=meal['protein']
        for item in meal['ingredients']:
            ingredients.add(item['name'])
            if item['section']=='produce' and item['name'] not in {'garlic','ginger','onion','firm tofu','tempeh'}:
                produce.add(item['name'])
    return dict(checkout=checkout,portion=round(sum(m['cost'] for m in meals),2),recipes=len(counts),
                ingredients=len(ingredients),produce=len(produce),max_repeats=max(counts.values(),default=0),
                repetition=sum(max(0,count-3)**2 for count in counts.values()),
                daily=dict(daily),package_remainder_cost=round(sum(r['extra_quantity']/r['package_quantity']*r['package_price'] for r in rows),2))


def _loss(plan,ctx,detail):
    days=list(detail['daily'].values());target=ctx.calorie_target;pro=protein_target(ctx)
    value=0.0
    if days and target:
        avg=sum(d['calories'] for d in days)/len(days)
        value+=4*abs(avg-target)/target + sum(abs(d['calories']-target)/target for d in days)/len(days)
    elif days:
        # A scoring reference for substantial main meals, not a medical target or validation rule.
        value+=.6*sum(abs(d['calories']-2000)/2000 for d in days)/len(days)
    if days and pro:
        value+=3*sum(max(0,pro-d['protein'])/pro for d in days)/len(days)
    value+=1.5*detail['repetition'] + .65*max(0,variety_target(ctx)-detail['recipes'])
    value-=.035*min(12,detail['produce'])
    value+=.12*sum(m['name'] in ctx.avoid for m in plan['meals'])
    value-=.1*sum(m['name'] in ctx.liked for m in plan['meals'])
    pantry={p['name'].lower() for p in ctx.pantry};used={i['name'] for m in plan['meals'] for i in m['ingredients']}
    value-=.08*len(pantry & used)
    # Confirmed leftovers remain a preference through local improvement too.
    leftovers={name.lower() for name in ctx.leftovers}
    for name in leftovers:
        value-=.8*min(3,sum(any(i['name'].lower()==name for i in m['ingredients']) for m in plan['meals']))
    # Existing pantry stock and partial weeks can legitimately make shopping tiny.
    if ctx.checkout_budget and not ctx.pantry and len(plan['meals'])>=14:
        value+=2*max(0,.75*ctx.budget-detail['checkout'])/ctx.budget
    value+=.35*detail['package_remainder_cost']/max(ctx.budget,1)
    return value


def _goal_distance(detail, ctx):
    days=list(detail['daily'].values())
    if not days:return 0
    distance=0.0
    if ctx.calorie_target:
        target=ctx.calorie_target
        avg=sum(day['calories'] for day in days)/len(days)
        distance+=abs(avg-target)/target
        distance+=sum(abs(day['calories']-target)/target for day in days)/len(days)
    target=protein_target(ctx)
    if target:
        distance+=sum(max(0,target-day['protein'])/target for day in days)/len(days)
    return distance


def improve_plan(plan,ctx,recipes,max_evaluations=420):
    """Improve a fully valid proposal; never rescue or hide a hard provider failure."""
    from app.services.validators import validate_full,check_goal
    original,hard,soft=validate_full(plan,ctx)
    if hard or not original['meals']:
        return plan
    eligible=eligible_recipes(ctx,recipes)
    pools=candidate_pool(ctx,eligible,per_slot=18)
    pins={(m['day'],m['slot']) for m in ctx.pinned}
    current=copy.deepcopy(original);detail=metrics(current,ctx);loss=_loss(current,ctx,detail)
    goals=len(check_goal(current,ctx))
    distance=_goal_distance(detail,ctx) if goals else 0
    current_key=(len(soft),goals,distance,loss);evaluations=0;accepted=0
    order=list(range(len(current['meals'])));random.Random(ctx.seed).shuffle(order)
    for _ in range(2):
        changed=False
        for index in order:
            meal=current['meals'][index]
            if (meal['day'],meal['slot']) in pins:continue
            best=None; proposals=[]
            for recipe in pools.get(meal['slot'],[]):
                if recipe['name']==meal['name']:continue
                if evaluations>=max_evaluations:break
                evaluations+=1
                candidate={'meals':list(current['meals'])}
                replacement={key:copy.deepcopy(value) for key,value in recipe.items() if key!='slots'}
                replacement.update(day=meal['day'],slot=meal['slot']);candidate['meals'][index]=replacement
                try:info=metrics(candidate,ctx)
                except (KeyError,ValueError):continue
                total=info['checkout'] if ctx.checkout_budget else info['portion']
                if total>ctx.budget+.001:continue
                candidate_loss=_loss(candidate,ctx,info);candidate_goals=len(check_goal(candidate,ctx))
                candidate_distance=_goal_distance(info,ctx) if candidate_goals else 0
                if (candidate_goals,candidate_distance,candidate_loss)>=(goals,distance,loss):continue
                proposals.append(((candidate_goals,candidate_distance,candidate_loss),candidate,info))
            # Rank cheaply first; run the full scheduler/validator only on the
            # best few alternatives, rather than every rejected candidate.
            for (candidate_goals,candidate_distance,candidate_loss),candidate,info in sorted(proposals,key=lambda item:item[0])[:4]:
                normalized,errors,warnings=validate_full(candidate,ctx)
                key=(len(warnings),candidate_goals,candidate_distance,candidate_loss)
                if not errors and key<current_key:
                    best=(key,normalized,info,candidate_goals)
                    break
            if best:
                current_key,current,detail,goals=best;distance=current_key[2];loss=current_key[3];accepted+=1;changed=True
            if evaluations>=max_evaluations:break
        if not changed or evaluations>=max_evaluations:break
    ctx.quality_metrics=dict(version=1,recipes=detail['recipes'],ingredients=detail['ingredients'],
                             max_repeats=detail['max_repeats'],variety_target=variety_target(ctx),
                             checkout=detail['checkout'],preferred_range=[round(ctx.budget*.75,2),round(ctx.budget*.95,2)],
                             preferred_range_applies=not bool(ctx.pantry) and len(current['meals'])>=14,
                             evaluated=evaluations,changes=accepted)
    return current
