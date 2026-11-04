"""Compute nutrients from a checked-in USDA snapshot and explicit gram measures."""
import json
from pathlib import Path

DATA=json.loads((Path(__file__).parents[1]/'data/ingredients.json').read_text())
INGREDIENTS=DATA['ingredients']


def calculate(ingredients):
    calories=protein=0.0
    for ingredient in ingredients:
        name=ingredient['name'].lower().strip();unit=ingredient['unit'].lower().strip()
        record=INGREDIENTS.get(name)
        if not record or unit not in record['grams_per_unit']:
            raise ValueError(f'No verified nutrient mapping for {name} ({unit}).')
        grams=ingredient['quantity']*record['grams_per_unit'][unit]
        calories+=grams*record['calories_per_100g']/100
        protein+=grams*record['protein_per_100g']/100
    return round(calories),round(protein,1)


def catalog_plan(raw,ctx):
    """The model selects recipes; it cannot invent nutrients, prices or steps."""
    import copy
    from app.services.catalog import RECIPES
    lookup={r['name']:r for r in RECIPES}
    pins={(p['day'],p['slot']):p for p in ctx.pinned}
    if not isinstance(raw,dict) or not isinstance(raw.get('meals'),list):raise ValueError('Return a meals list.')
    out=[]
    for selected in raw['meals']:
        name=selected.get('name');day=selected.get('day');slot=selected.get('slot')
        if (day,slot) in pins:
            if name!=pins[(day,slot)]['name']:raise ValueError('A pinned recipe must stay unchanged.')
            meal=copy.deepcopy(pins[(day,slot)])
        else:
            recipe=lookup.get(name)
            if not recipe or slot not in recipe['slots']:raise ValueError(f'Choose an approved recipe for {slot}: {name}')
            meal={k:copy.deepcopy(v) for k,v in recipe.items() if k!='slots'}
            from app.services.pricing import apply_recipe_prices
            meal=apply_recipe_prices(meal,ctx.price_offers)
            meal.update(day=day,slot=slot)
        out.append(meal)
    return {'meals':out}


def evidence(meal):
    try:
        calories,protein=calculate(meal['ingredients'])
    except (ValueError,KeyError):return None
    if calories!=meal.get('calories') or abs(protein-meal.get('protein',0))>0.1:return None
    return [{'name':i['name'],'grams':round(i['quantity']*INGREDIENTS[i['name']]['grams_per_unit'][i['unit']],1),**INGREDIENTS[i['name']]} for i in meal['ingredients']]
