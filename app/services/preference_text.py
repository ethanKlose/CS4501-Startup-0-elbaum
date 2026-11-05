"""Conservative offline extraction with explicit notices for unsupported notes."""
import re
from app.services.types import WEEKDAYS

TRIGGER = re.compile(r"\b(?:no|without|avoid|skip|hate|dislike|allergic to|allergy to|cannot eat|can't eat|don't eat|do not eat|don't like|do not like|not a fan of|never)\s+", re.I)
DIETS = {'vegan': 'vegan', 'vegetarian': 'vegetarian', 'gluten[- ]free': 'gluten_free',
         'dairy[- ]free': 'dairy_free', 'nut[- ]free': 'nut_allergy', 'egg[- ]free': 'egg_free', 'halal': 'halal'}


def interpret(text):
    text=(text or '').replace('’', "'").lower().strip()
    excluded=set();caps={};warnings=[]
    # Commas carry a food-list trigger; a sentence boundary ends that list.
    for sentence in re.split(r'[.;\n]+', text):
        food_list=False
        for clause in re.split(r",|\band\s+(?=i\b)",sentence):
            clause=clause.strip()
            if not clause:continue
            days=[i for i,d in enumerate(WEEKDAYS) if re.search(r'\b'+d.lower()+r's?\b|\b'+d[:3].lower()+r's?\b',clause)]
            recognized=False
            for pattern,key in DIETS.items():
                if re.search(r'\b'+pattern+r'\b',clause) and not re.search(r"\b(?:not|no longer)\s+(?:a\s+)?"+pattern+r'\b',clause):
                    excluded.add(key);recognized=True
            if 'cook' in clause:
                food_list=False
                zero=bool(re.search(r"\b(?:no cooking|not cook|can't cook|cannot cook|don't cook|do not cook)\b",clause))
                number=re.search(r'\b(\d+)\s*(?:minutes?|mins?)\b',clause)
                reluctant=bool(re.search(r'\b(?:hate|dislike)\s+cooking\b',clause))
                if zero or number or reluctant:
                    limit=0 if zero else int(number.group(1)) if number else 15
                    if 0<=limit<=480 and (days or re.search(r'\b(?:each|every|per) day|\bdaily\b',clause)):
                        for day in days or range(7):caps[str(day)]=min(caps.get(str(day),480),limit)
                    else:warnings.append('Confirm the days and cooking minutes in your schedule; part of your note could not be applied.')
                elif not re.fullmatch(r"i (?:can|will) cook on (?:[a-z ,]+)",clause):
                    warnings.append('Part of your cooking note was not applied. Set explicit days and minutes in the schedule.')
                continue
            trigger=TRIGGER.search(clause)
            if trigger or food_list:
                items=clause[trigger.end():] if trigger else clause
                # "no fish and no dairy" and comma/or lists share the same rule.
                for item in re.split(r'\band\b|\bor\b|/|&',items):
                    item=TRIGGER.sub('',item).strip()
                    item=re.sub(r'^(?:any|all|the)\s+','',item).strip()
                    if item and not re.search(r'\b(?:except|unless|sometimes|if)\b',item):
                        excluded.add(item);recognized=True
                    elif item:warnings.append('A conditional food restriction needs review. Use the diet checkboxes or list ingredients to avoid without exceptions.')
                food_list=True
            elif not recognized:
                food_list=False
                warnings.append('Some extra preferences could not be converted into rules. Review the understood restrictions and use the explicit diet and schedule controls.')
    # Unknown food terms must not quietly appear to have been verified.
    from app.services.catalog import RECIPES
    from app.services.diet import term_hits
    for term in excluded:
        if not any(term_hits(i['name'],term) for r in RECIPES for i in r['ingredients']):
            warnings.append(f"The recipe catalog does not recognize '{term}'. Review this restriction before relying on the plan.")
    out={'excluded':sorted(excluded),'day_minutes_cap':caps}
    if warnings:out['warnings']=sorted(set(warnings))
    return out


def merge_extractions(local,model):
    """Never let a model response erase explicit locally recognized constraints."""
    caps=dict(model['day_minutes_cap'])
    for day,value in local['day_minutes_cap'].items():caps[day]=min(caps.get(day,480),value)
    out={'excluded':sorted(set(local['excluded'])|set(model['excluded'])),'day_minutes_cap':caps}
    if local.get('warnings'):out['warnings']=local['warnings']
    return out
