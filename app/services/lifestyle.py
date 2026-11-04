"""Student constraints are deterministic rules, not model suggestions."""
import re

EQUIPMENT={'stove':'Stove','oven':'Oven','microwave':'Microwave','toaster':'Toaster','blender':'Blender','fridge':'Refrigerator','freezer':'Freezer'}


def required_equipment(meal):
    text=' '.join([meal.get('name','')]+meal.get('steps',[])).lower()
    needed=set()
    if re.search(r'\b(roast|bake|baked|oven)\b',text):needed.add('oven')
    if re.search(r'\b(simmer|boil|saute|sauté|pan|sear|fry|stir-fry|cook rice|scramble|scrambled)\b',text):needed.add('stove')
    if re.search(r'\b(blend|smoothie)\b',text):needed.add('blender')
    if re.search(r'\b(toast|toasted)\b',text):needed.add('toaster')
    if 'overnight' in text or 'refrigerate' in text:needed.add('fridge')
    return needed


def violations(meal,ctx):
    errors=[]
    if ctx.equipment is not None:
        missing=required_equipment(meal)-set(ctx.equipment)
        if missing:errors.append(f"'{meal['name']}' needs unavailable equipment: {', '.join(sorted(missing))}.")
    if ctx.cooking_skill=='beginner' and meal.get('cook_minutes',0)>25:
        errors.append(f"'{meal['name']}' exceeds the beginner recipe limit of 25 minutes.")
    return errors
