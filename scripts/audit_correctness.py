"""Offline correctness benchmark. Configurations and seeds are not participants."""
import argparse
import csv
import json
from pathlib import Path
import statistics
import time
from app.services.llm import FakeLLM
from app.services.planner import run_with_retries,PlanFailed
from app.services.pricing import plan_checkout
from app.services.types import PlanContext,DayCtx
from app.services.validators import validate_full

SCENARIOS=[
    ('baseline_2000kcal',dict(goal='calorie_target',calorie_target=2000)),
    *[(f'budget_{b}',dict(budget=b)) for b in (30,40,60,80)],
    ('vegan_2000kcal',dict(restrictions=['vegan'],goal='calorie_target',calorie_target=2000)),
    ('vegetarian_2000kcal',dict(restrictions=['vegetarian'],goal='calorie_target',calorie_target=2000)),
    ('gluten_free',dict(restrictions=['gluten_free'])),
    ('vegan_gluten_free',dict(restrictions=['vegan','gluten_free'])),
    ('dairy_free_nut_allergy',dict(restrictions=['dairy_free','nut_allergy'])),
    ('shellfish_egg_free',dict(restrictions=['shellfish_allergy','egg_free'])),
    ('high_protein',dict(goal='high_protein')),
    ('no_cook_wed_thu',dict(days=[DayCtx(i,0 if i in (2,3) else 45) for i in range(7)])),
    ('zero_minutes_every_day',dict(days=[DayCtx(i,0) for i in range(7)],allow_pre_week=False)),
    ('microwave_beginner',dict(equipment=['microwave','fridge'],allow_freezer=False,cooking_skill='beginner')),
    ('no_equipment',dict(equipment=[],allow_freezer=False,prep_style='daily',allow_pre_week=False)),
    ('evening_windows',dict(cooking_windows={str(i):[[1020,1140]] for i in range(7)},allow_pre_week=False)),
    ('dining_hall_lunches',dict(goal='calorie_target',calorie_target=2000,external_slots=[dict(day=i,slot='lunch') for i in range(5)])),
    ('thursday_dinner_start',dict(days=[DayCtx(i,45,skipped=i<3) for i in range(7)],allow_pre_week=False,earliest_day=3,earliest_minute=1020,external_slots=[dict(day=3,slot=s,past=True) for s in ('breakfast','lunch')])),
    ('3000kcal_target',dict(goal='calorie_target',calorie_target=3000)),
]


def evaluate(repeats=3):
    import copy
    rows=[]
    for name,overrides in SCENARIOS:
        for seed in range(1,repeats+1):
            args=dict(budget=150,days=[DayCtx(i,45) for i in range(7)],checkout_budget=True,seed=seed)
            args.update(copy.deepcopy(overrides));ctx=PlanContext(**args)
            start=time.perf_counter();row=dict(scenario=name,seed=seed)
            try:
                plan,attempts,warnings=run_with_retries(FakeLLM(),ctx)
                _,hard,soft=validate_full(plan,ctx)
                checkout,_=plan_checkout(plan['meals'],ctx.pantry,ctx.price_offers)
                row.update(accepted=True,all_checks_satisfied=not hard and not soft and not warnings,attempts=attempts,warnings=warnings,errors=hard,meals=len(plan['meals']),checkout_usd=checkout,unique_recipes=len({m['name'] for m in plan['meals']}))
            except PlanFailed as e:
                row.update(accepted=False,all_checks_satisfied=False,attempts=len(ctx.generation_trace),errors=e.errors,warnings=[])
            row['seconds']=round(time.perf_counter()-start,6);rows.append(row)
    return dict(engine='fake',human_participants=0,configurations=len(SCENARIOS),repeats=repeats,runs=len(rows),
                accepted=sum(r['accepted'] for r in rows),all_checks_satisfied=sum(r['all_checks_satisfied'] for r in rows),
                median_generation_seconds=statistics.median(r['seconds'] for r in rows),results=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repeats',type=int,default=3);parser.add_argument('--output',default='evals/audit-after.json')
    args=parser.parse_args()
    if not 1<=args.repeats<=10:parser.error('repeats must be 1..10')
    report=evaluate(args.repeats);path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    with path.with_suffix('.csv').open('w',newline='') as f:
        fields=sorted(set().union(*(r.keys() for r in report['results'])))
        writer=csv.DictWriter(f,fields);writer.writeheader()
        writer.writerows({k:json.dumps(v) if isinstance(v,list) else v for k,v in r.items()} for r in report['results'])
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))
