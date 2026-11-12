"""Reproducible offline quality checks; configurations are not user studies.

Run: python -m scripts.benchmark_planner_quality --output test-results/planner-quality.json
Uses FakeLLM directly, never calls a paid provider or changes the app database.
"""
import argparse
import json
import time
from collections import Counter
from pathlib import Path

from app.services.llm import FakeLLM
from app.services.pricing import plan_checkout
from app.services.types import DayCtx, PlanContext
from app.services.validators import validate_full


def evaluate():
    rows = []
    for budget in (50, 100, 150):
        for restrictions in ([], ['vegan']):
            for seed in (1, 23):
                context = PlanContext(budget=budget, days=[DayCtx(day, 45) for day in range(7)],
                                      restrictions=restrictions, checkout_budget=True, seed=seed,
                                      goal='calorie_target', calorie_target=2000)
                started = time.perf_counter()
                plan = FakeLLM().generate_plan(context)
                _, hard, soft = validate_full(plan, context)
                checkout, _ = plan_checkout(plan['meals'], context.pantry, context.price_offers)
                names = Counter(meal['name'] for meal in plan['meals'])
                rows.append(dict(budget=budget, restrictions=restrictions, seed=seed,
                                 checkout=checkout, portion=round(sum(m['cost'] for m in plan['meals']), 2),
                                 recipes=len(names), ingredients=len({i['name'] for m in plan['meals'] for i in m['ingredients']}),
                                 max_repeats=max(names.values(), default=0),
                                 calories=round(sum(m['calories'] for m in plan['meals']) / 7),
                                 protein=round(sum(m['protein'] for m in plan['meals']) / 7, 1),
                                 hard=hard, soft=soft, seconds=round(time.perf_counter()-started, 3)))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='test-results/planner-quality.json')
    args = parser.parse_args()
    rows = evaluate()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(engine='fake', runs=len(rows), hard_valid=sum(not r['hard'] for r in rows),
                          all_checks_satisfied=sum(not r['hard'] and not r['soft'] for r in rows),
                          paid_requests=0, output=str(path))))
    raise SystemExit(1 if any(row['hard'] for row in rows) else 0)
