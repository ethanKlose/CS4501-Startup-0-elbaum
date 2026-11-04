"""Whole-package checkout estimates, with user-entered price provenance."""
import copy
import math
from statistics import median
from app.services.nutrition import INGREDIENTS
from app.services import grocery


def reference_offers():
    from app.services.catalog import RECIPES
    values={}
    for recipe in RECIPES:
        for i in recipe['ingredients']:
            values.setdefault((i['name'],i['unit']),[]).append(i['cost']/i['quantity'])
    offers={}
    for (name,unit),prices in values.items():
        size={'each':12 if name=='eggs' else 1,'slice':20,'oz':16,'cup':4,'tbsp':16,'tsp':24,'can':1,'block':1,'scoop':15,'leaf':10,'stalk':8,'clove':12}.get(unit,1)
        offers[grocery.item_key(name,unit)]={'name':name,'unit':unit,'package_quantity':size,'package_price':round(median(prices)*size,2),'source':'Built-in demo estimate','observed_on':None}
    return offers


def apply_recipe_prices(recipe,offers):
    recipe=copy.deepcopy(recipe)
    all_offers=reference_offers();all_offers.update(offers or {})
    for i in recipe['ingredients']:
        offer=all_offers.get(grocery.item_key(i['name'],i['unit']))
        if offer:i['cost']=round(i['quantity']*offer['package_price']/offer['package_quantity'],2)
    recipe['cost']=round(sum(i['cost'] for i in recipe['ingredients']),2)
    return recipe


def checkout(items,overrides=None):
    offers=reference_offers();offers.update(overrides or {})
    rows=[]
    for item in items:
        offer=offers.get(item['key'])
        if not offer:raise ValueError('No package price for '+item['name']+' ('+item['unit']+'). Add a local offer first.')
        quantity=offer['package_quantity'];count=max(0,math.ceil((item['quantity']-1e-9)/quantity))
        rows.append(dict(item,packages=count,package_quantity=quantity,package_price=offer['package_price'],checkout_cost=round(count*offer['package_price'],2),extra_quantity=round(count*quantity-item['quantity'],2),price_source=offer['source'],observed_on=offer.get('observed_on')))
    return rows


def plan_checkout(meals,pantry,offers):
    items=grocery.apply_pantry(grocery.build_list(meals),pantry)
    rows=checkout(items,offers)
    return round(sum(r['checkout_cost'] for r in rows),2),rows
