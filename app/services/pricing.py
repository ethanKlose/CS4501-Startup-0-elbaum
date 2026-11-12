"""Whole-package checkout estimates, with user-entered price provenance."""
import copy
import math
import json
from pathlib import Path
from app.services.nutrition import INGREDIENTS
from app.services import grocery


_REFERENCE = json.loads((Path(__file__).parents[1] / 'data/package_prices.json').read_text())['offers']


def reference_offers():
    """Prices do not drift when a new recipe is added; callers receive their own copy."""
    return copy.deepcopy(_REFERENCE)


def apply_recipe_prices(recipe,offers):
    recipe=copy.deepcopy(recipe)
    all_offers=dict(_REFERENCE);all_offers.update(offers or {})
    for i in recipe['ingredients']:
        offer=all_offers.get(grocery.item_key(i['name'],i['unit']))
        if offer:i['cost']=round(i['quantity']*offer['package_price']/offer['package_quantity'],2)
    recipe['cost']=round(sum(i['cost'] for i in recipe['ingredients']),2)
    return recipe


def checkout(items,overrides=None,allow_unknown=False):
    offers=dict(_REFERENCE);offers.update(overrides or {})
    rows=[]
    for item in items:
        offer=offers.get(item['key'])
        if not offer:
            if not allow_unknown:raise ValueError('No package price for '+item['name']+' ('+item['unit']+'). Unpin the legacy recipe or choose a supported recipe.')
            rows.append(dict(item,packages=1,package_quantity=item['quantity'],package_price=item['cost'],checkout_cost=item['cost'],extra_quantity=0,price_source='Legacy portion estimate; package size unknown',observed_on=None,unknown_package=True))
            continue
        quantity=offer['package_quantity'];count=max(0,math.ceil((item['quantity']-1e-9)/quantity))
        rows.append(dict(item,packages=count,package_quantity=quantity,package_price=offer['package_price'],checkout_cost=round(count*offer['package_price'],2),extra_quantity=round(count*quantity-item['quantity'],2),price_source=offer['source'],observed_on=offer.get('observed_on')))
    return rows


def plan_checkout(meals,pantry,offers):
    items=grocery.apply_pantry(grocery.build_list(meals),pantry)
    rows=checkout(items,offers)
    return round(sum(r['checkout_cost'] for r in rows),2),rows
