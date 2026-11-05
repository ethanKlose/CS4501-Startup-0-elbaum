"""Search low-variety baskets using whole packages before declaring no plan found."""
import copy
import itertools
import math
from collections import Counter

from app.services import grocery
from app.services.diet import meal_violations
from app.services.lifestyle import violations
from app.services.pricing import apply_recipe_prices, reference_offers
from app.services.types import SLOTS


def affordable_fallback(ctx, recipes):
    """Enumerate one recipe per open slot type, retaining pins and actual prices.

    This deliberately bounded search establishes useful cheap feasible seeds;
    it is not a proof that every possible diverse weekly plan was considered.
    """
    from app.services.validators import validate_full
    pins={(m['day'],m['slot']):m for m in ctx.pinned}
    slots=[(d.weekday,s) for d in ctx.active_days() for s in ctx.slots_for(d.weekday) if (d.weekday,s) not in pins]
    counts=Counter(s for _,s in slots)
    allowed=[apply_recipe_prices(r,ctx.price_offers) for r in recipes
             if not meal_violations(r,ctx.restrictions,ctx.excluded) and not violations(r,ctx) and r['name'] not in ctx.disliked]
    kinds=[s for s in SLOTS if counts[s]]
    pools=[[r for r in allowed if s in r['slots']] for s in kinds]
    if any(not pool for pool in pools):return None
    offers=reference_offers();offers.update(ctx.price_offers)

    def totals(meals):
        amounts={}
        for meal,n in meals:
            for i in meal['ingredients']:
                k=grocery.item_key(i['name'],i['unit'])
                amounts[k]=amounts.get(k,0)+n*i['quantity']
        return amounts

    opening=totals((m,1) for m in pins.values())
    stock={};unlimited=set()
    for p in ctx.pantry:
        for key,offer in offers.items():
            name,unit=key.rsplit('|',1)
            if grocery._same_food(p['name'],name):
                if p.get('quantity') is None:unlimited.add(key)
                elif (p.get('unit') or '').lower().strip()==unit:stock[key]=stock.get(key,0)+p['quantity']
    options=[[(r,totals([(r,counts[s])])) for r in pool] for s,pool in zip(kinds,pools)]
    candidates=[]
    for combo in itertools.product(*options):
        portion=sum(m['cost'] for m in pins.values())+sum(r['cost']*counts[s] for s,(r,_) in zip(kinds,combo))
        if not ctx.checkout_budget and portion>ctx.budget+.001:continue
        amounts=dict(opening)
        for _,vector in combo:
            for k,q in vector.items():amounts[k]=amounts.get(k,0)+q
        cost=0
        for k,q in amounts.items():
            if k in unlimited:continue
            offer=offers.get(k)
            if not offer:cost=math.inf;break
            q=max(0,round(q,2)-stock.get(k,0))
            cost+=math.ceil((q-1e-9)/offer['package_quantity'])*offer['package_price']
        if cost<=ctx.budget+.001:candidates.append((round(cost,2),combo))
    candidates.sort(key=lambda item:item[0])
    best=None
    for _,combo in candidates:
        by_slot={s:r for s,(r,_) in zip(kinds,combo)}
        meals=copy.deepcopy(list(pins.values()))
        for day,slot in slots:
            meal=copy.deepcopy({k:v for k,v in by_slot[slot].items() if k!='slots'})
            meals.append(dict(meal,day=day,slot=slot))
        plan,hard,soft=validate_full({'meals':meals},ctx)
        if hard:continue
        if not soft:return plan
        if best is None or len(soft)<best[0]:best=(len(soft),plan)
        # Keep fallback latency bounded once a usable low-cost seed exists.
        if best and len(candidates)>100:break
    return best[1] if best else None
