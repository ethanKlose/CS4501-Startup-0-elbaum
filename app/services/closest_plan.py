"""Return the closest catalog-backed plan without relaxing food exclusions or integrity."""
import math
import time
from dataclasses import replace
from app.services import validators as v
from app.services.schema import parse_plan
from app.services.pricing import plan_checkout
from app.services.nutrition_goals import protein_target
from app.services.planner import PlanFailed


class PlanningBlocked(PlanFailed):
    redirect_to_preferences = True


def assess(raw, ctx):
    plan, errors = parse_plan(raw)
    if errors:
        return plan, errors, [], None
    from app.services.nutrition import catalog_plan
    try:
        trusted, trusted_errors = parse_plan(catalog_plan(plan,ctx))
        if trusted_errors or trusted != plan:
            errors.append('Recipe content differs from the trusted catalog or pinned snapshot.')
    except (ValueError,KeyError,TypeError):
        errors.append('Only approved catalog recipes or unchanged pins can be used.')
    # Budget, nutrition and timing are explicit reviewable deviations. Food,
    # equipment, coverage, pins, cost arithmetic and known prices stay strict.
    for check in (v.check_coverage, v.check_cost_integrity, v.check_diet, v.check_pinned, v.check_disliked):
        errors.extend(check(plan, ctx))
    try:
        shopping = plan_checkout(plan['meals'], ctx.pantry, ctx.price_offers)[0]
    except (ValueError, KeyError, TypeError):
        errors.append('A recipe has no verifiable package-price data.')
        shopping = None
    if errors:
        return plan, errors, [], None
    daily = {}
    for meal in plan['meals']:
        row = daily.setdefault(meal['day'], {'calories': 0, 'protein': 0.0})
        row['calories'] += meal['calories']; row['protein'] += meal['protein']
    n = max(1, len(daily)); cal = sum(r['calories'] for r in daily.values())/n
    pro = sum(r['protein'] for r in daily.values())/n
    target = protein_target(ctx)
    total = shopping if ctx.checkout_budget else v.plan_total(plan)
    over = max(0, total-ctx.budget)
    warnings = []
    if over > .005:
        warnings.append(f'Estimated shopping is ${total:.2f}: ${over:.2f} ({over/ctx.budget:.1%}) over your ${ctx.budget:.2f} budget. Review before shopping.')
    if not ctx.external_slots and ctx.goal in ('calorie_target', 'protein_calorie') and ctx.calorie_target:
        gap = cal-ctx.calorie_target
        if abs(gap) >= .5:
            warnings.append(f'Calories average {cal:.0f} kcal/day versus {ctx.calorie_target}: {abs(gap):.0f} kcal/day ({abs(gap)/ctx.calorie_target:.1%}) {"below" if gap<0 else "above"} target.')
    if not ctx.external_slots and target and pro < target-.05:
        warnings.append(f'Protein averages {pro:.1f}g/day versus {target}g: {target-pro:.1f}g/day ({(target-pro)/target:.1%}) below target.')
    # Keep day-specific goal, outside-meal knowledge and cooking-time notices.
    warnings += v.check_goal(plan, ctx)+v.check_schedule(plan, ctx)+v.check_cooking_deadlines(plan, ctx)
    days = [dict(day=day, calories=row['calories'], protein=round(row['protein'],1),
                 calorie_difference=round(row['calories']-ctx.calorie_target) if ctx.calorie_target else None,
                 protein_shortfall=round(max(0,target-row['protein']),1) if target else None)
            for day,row in sorted(daily.items())]
    score = 4*over/max(ctx.budget,1)
    if ctx.calorie_target and not ctx.external_slots:
        score += 3*sum(abs(r['calories']-ctx.calorie_target)/ctx.calorie_target for r in daily.values())/n
    if target and not ctx.external_slots:
        score += 3*sum(max(0,target-r['protein'])/target for r in daily.values())/n
    score += .1*(len(v.check_schedule(plan,ctx))+len(v.check_cooking_deadlines(plan,ctx)))
    report = dict(shopping=shopping, budget=ctx.budget, over_budget=round(over,2),
                  average_calories=round(cal), calorie_target=ctx.calorie_target,
                  average_protein=round(pro,1), protein_target=target, days=days,
                  score=round(score,6), unique_recipes=len({m['name'] for m in plan['meals']}))
    return plan, [], list(dict.fromkeys(warnings+list(ctx.preference_warnings))), report


def select_plan(llm, ctx):
    from app.services.llm import FakeLLM
    if not math.isfinite(ctx.budget) or ctx.budget < 30 or ctx.budget > 10000 or (ctx.calorie_target and not 1200 <= ctx.calorie_target <= 4500):
        raise PlanningBlocked('These settings are outside the supported planning range. Use a weekly budget of $30–$10,000 and a calorie goal of 1,200–4,500 kcal/day. Please revise your preferences.')
    candidates=[]; failures=[]; requested=getattr(llm,'name','custom'); started=time.perf_counter()
    def consider(raw, source):
        plan, hard, warnings, report = assess(raw, ctx)
        ctx.generation_trace.append(dict(attempt=len(ctx.generation_trace)+1,source=source,
            seconds=round(time.perf_counter()-started,3),hard_errors=hard,soft_warnings=warnings))
        if hard: failures.extend(hard);return
        key=(report['score'], max(0,ctx.budget*.5-report['shopping'])/max(ctx.budget,1),-report['unique_recipes'])
        candidates.append((key,plan,warnings,report,source))
    try:
        consider(llm.generate_plan(ctx, []), requested)
    except Exception:
        failures.append('Configured generator unavailable or returned invalid data.')
        ctx.generation_trace.append(dict(attempt=1,source=requested,hard_errors=['Generator unavailable; local fallback requested.'],soft_warnings=[]))
    # One provider planning attempt; local comparisons do not spend API tokens.
    # Relaxed search budgets generate alternatives, not a hidden change to the
    # user's budget. Every candidate is measured against the ORIGINAL settings.
    for index, multiplier in enumerate((1, 1.25, 1.6)):
        local=replace(ctx,budget=min(10000,max(30,ctx.budget*multiplier)),seed=ctx.seed+index*7919,
                      generation_trace=[],quality_metrics={})
        try:consider(FakeLLM().generate_plan(local),'catalog_fallback')
        except Exception:continue
    if not candidates:
        raise PlanningBlocked('No complete plan could be assembled without breaking your food exclusions, kitchen rules, pins or recipe-data checks. Please adjust those preferences; no unsafe or incomplete plan was substituted.', failures[:8])
    _, plan, warnings, report, source=min(candidates,key=lambda item:item[0])
    report.update(source=source,requested_engine=requested)
    ctx.closest_metrics=report
    from collections import Counter
    counts=Counter(m['name'] for m in plan['meals'])
    ctx.quality_metrics=dict(version=2,recipes=len(counts),ingredients=len({i['name'] for m in plan['meals'] for i in m['ingredients']}),max_repeats=max(counts.values(),default=0),checkout=report['shopping'])
    if source=='catalog_fallback' and requested not in ('fake','catalog_fallback'):
        warnings=['This plan was built locally from approved recipes; the configured AI did not supply the selected plan.']+warnings
    return plan, len(ctx.generation_trace), warnings
