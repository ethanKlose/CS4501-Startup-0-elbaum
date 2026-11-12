"""Soft per-meal diversity goals and bounded, token-free catalog repair."""
import copy
import math
from collections import Counter
from app.services.types import SLOTS
from app.services.nutrition_goals import protein_target
from app.services.pricing import plan_checkout

TARGETS={'breakfast':3,'lunch':3,'dinner':4}


def available_recipes(ctx):
    from app.services.catalog import RECIPES
    from app.services.planning_quality import eligible_recipes
    recipes=eligible_recipes(ctx,RECIPES)
    return {slot:[r for r in recipes if slot in r['slots']] for slot in SLOTS}


def describe(plan,ctx,available):
    pins={(m['day'],m['slot']) for m in ctx.pinned};rows={};notices=[];penalty=0.0
    for slot in SLOTS:
        meals=sorted([m for m in plan['meals'] if m['slot']==slot],key=lambda m:m['day'])
        n=len(meals);counts=Counter(m['name'] for m in meals)
        fixed=Counter(m['name'] for m in meals if (m['day'],slot) in pins)
        choices={r['name'] for r in available[slot]}|set(fixed)
        desired=min(TARGETS[slot],n)
        attainable=min(desired,len(choices),len(fixed)+n-sum(fixed.values()))
        cap=max(3,math.ceil(n/max(1,len(choices))))
        excess=sum(max(0,c-cap)**2 for c in counts.values())-sum(max(0,c-cap)**2 for c in fixed.values())
        streak=0;previous=None;run=0
        for meal in meals:
            same=previous and meal['day']==previous['day']+1 and meal['name']==previous['name']
            run=run+1 if same else 1
            if len(choices)>1 and run>2 and not ((meal['day'],slot) in pins and (previous['day'],slot) in pins):streak+=1
            previous=meal
        missing=max(0,attainable-len(counts))
        cost=.6*max(0,excess)/max(n,1)+.6*missing/max(attainable,1)+.3*streak/max(n,1)
        rows[slot]=dict(planned=n,distinct=len(counts),target=attainable,desired=desired,
                        max_repeats=max(counts.values(),default=0),repeat_limit=cap,penalty=round(cost,6))
        penalty+=cost
        if missing or excess>0 or streak:
            notices.append(f'{slot.capitalize()} variety: {len(counts)} different recipes across {n} meals; aiming for {attainable}, usually at most 3 repeats and 2 consecutive days. Budget, targets, preparation or pins limited the repair.')
        elif attainable<desired:
            notices.append(f'{slot.capitalize()} variety target adjusted from {desired} to {attainable}: eligible recipes or pinned meals limit the choices.')
    all_counts=Counter(m['name'] for m in plan['meals'])
    pinned_counts=Counter(m['name'] for m in plan['meals'] if (m['day'],m['slot']) in pins)
    names={r['name'] for pool in available.values() for r in pool}|set(pinned_counts)
    cap=max(3,math.ceil(len(plan['meals'])/max(1,len(names))))
    excess=sum(max(0,c-cap)**2 for c in all_counts.values())-sum(max(0,c-cap)**2 for c in pinned_counts.values())
    global_penalty=.3*max(0,excess)/max(1,len(plan['meals']))
    if excess>0:notices.append('Some dishes repeat more than '+str(cap)+' times across meal types; the remaining repetition is shown rather than blocking your plan.')
    return dict(by_slot=rows,penalty=round(penalty+global_penalty,6),notices=notices,global_penalty=global_penalty,repeat_limit=cap,max_repeats=max(all_counts.values(),default=0))


def day_totals(plan):
    daily={}
    for meal in plan['meals']:
        row=daily.setdefault(meal['day'],dict(calories=0,protein=0,count=0))
        row['calories']+=meal['calories'];row['protein']+=meal['protein'];row['count']+=1
    return daily


def nutritional_distance(row,ctx):
    # Equal meal shares steer selection only; outside-meal nutrients stay unknown.
    fraction=row['count']/3;cal=ctx.calorie_target;protein=protein_target(ctx)
    cal_gap=max(0,abs(row['calories']-cal*fraction)-cal*fraction*.05)/(cal*fraction) if cal else 0
    pro_gap=max(0,protein*fraction*.98-row['protein'])/(protein*fraction) if protein else 0
    return 4*cal_gap+6*pro_gap


def objective(plan,ctx,shopping,available):
    days=list(day_totals(plan).values())
    total=shopping if ctx.checkout_budget else sum(m['cost'] for m in plan['meals'])
    return (8*max(0,total-ctx.budget)/max(ctx.budget,1)
            +sum(nutritional_distance(row,ctx) for row in days)/max(len(days),1)
            +describe(plan,ctx,available)['penalty'])


def nutrition_protected(candidate,current,ctx):
    old=day_totals(current);new=day_totals(candidate);target=protein_target(ctx)
    for day,row in new.items():
        before=old[day];fraction=row['count']/3
        if ctx.calorie_target:
            t=ctx.calorie_target*fraction
            if max(0,abs(row['calories']-t)-t*.10)>max(0,abs(before['calories']-t)-t*.10)+1:return False
        if target:
            floor=target*fraction*.95
            if max(0,floor-row['protein'])>max(0,floor-before['protein'])+.1:return False
    return True


def diversify(plan,ctx,available,assess,max_evaluations=320):
    """Repair repeats without touching pins, inventing recipes or calling AI."""
    current=copy.deepcopy(plan);_,errors,_,report=assess(current,ctx,available)
    if errors:return current
    pins={(m['day'],m['slot']) for m in ctx.pinned};evaluations=0
    ceiling=max(report['shopping'],ctx.budget*1.05)  # bounded, disclosed headroom
    for _ in range(2):
        changed=False
        order=sorted(range(len(current['meals'])),key=lambda i:-describe(current,ctx,available)['by_slot'][current['meals'][i]['slot']]['penalty'])
        for index in order:
            meal=current['meals'][index]
            if (meal['day'],meal['slot']) in pins:continue
            variety=describe(current,ctx,available)
            global_counts=Counter(m['name'] for m in current['meals'])
            if variety['by_slot'][meal['slot']]['penalty']<=0 and not (variety['global_penalty']>0 and global_counts[meal['name']]>variety['repeat_limit']):continue
            counts=Counter(m['name'] for m in current['meals'] if m['slot']==meal['slot'])
            pool=sorted(available[meal['slot']],key=lambda r:(counts[r['name']],abs(r['calories']-meal['calories'])/500+abs(r['protein']-meal['protein'])/40+r['cost']/10))[:24]
            base=objective(current,ctx,report['shopping'],available);proposals=[]
            for recipe in pool:
                if recipe['name']==meal['name']:continue
                if evaluations>=max_evaluations:break
                evaluations+=1
                replacement={k:copy.deepcopy(v) for k,v in recipe.items() if k!='slots'}
                replacement.update(day=meal['day'],slot=meal['slot'])
                candidate={'meals':list(current['meals'])};candidate['meals'][index]=replacement
                if not nutrition_protected(candidate,current,ctx):continue
                if describe(candidate,ctx,available)['penalty']>=variety['penalty']-1e-7:continue
                shopping=plan_checkout(candidate['meals'],ctx.pantry,ctx.price_offers)[0]
                if shopping>ceiling+.001:continue
                score=objective(candidate,ctx,shopping,available)
                if score<base-1e-7:proposals.append((score,candidate))
            for _,candidate in sorted(proposals,key=lambda item:item[0])[:3]:
                normalized,hard,_,updated=assess(candidate,ctx,available)
                if not hard and updated['score']<report['score']-1e-7:
                    current=normalized;report=updated;changed=True;break
            if evaluations>=max_evaluations:break
        if not changed or evaluations>=max_evaluations:break
    return current
