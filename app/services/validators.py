"""Validators: no LLM-generated plan reaches the user unless validate_full() reports no HARD errors.

Each check returns a list of plain-English errors. The same strings are fed back to the LLM
on retry, and (summarized) shown to the user if retries run out.
"""
from collections import Counter
from typing import List

from app.services.diet import meal_violations
from app.services.lifestyle import violations as lifestyle_violations
from app.services.schedule import Schedule, capacities, overbook_messages, schedule
from app.services.schema import MealIn, parse_plan
from app.services.types import SLOTS, WEEKDAYS, PlanContext
from app.services.timing import deadline_errors
from app.services.nutrition_goals import protein_target, selected_goals


HIGH_PROTEIN_DAILY_G = 75


def check_coverage(plan: dict, ctx: PlanContext) -> List[str]:
    errors = []
    seen = Counter((m["day"], m["slot"]) for m in plan["meals"])
    for d in ctx.days:
        for slot in SLOTS:
            n = seen.get((d.weekday, slot), 0)
            external=slot not in ctx.slots_for(d.weekday)
            if (d.skipped or external) and n:
                errors.append(f"{WEEKDAYS[d.weekday]} is marked as skipped; remove its meals.")
                break
            if not d.skipped and not external and n == 0:
                errors.append(f"Missing {slot} on {WEEKDAYS[d.weekday]}.")
            if n > 1:
                errors.append(f"More than one {slot} on {WEEKDAYS[d.weekday]}.")
    return errors


def plan_total(plan: dict) -> float:
    """Total recomputed from ingredient costs - never trust the LLM's own arithmetic."""
    return round(sum(i["cost"] for m in plan["meals"] for i in m["ingredients"]), 2)


def check_budget(plan: dict, ctx: PlanContext) -> List[str]:
    # Deduct owned stock before checking the cost of portions still needed.
    # The separate whole-package check also rejects an unaffordable basket.
    if ctx.checkout_budget:
        from app.services.grocery import build_list,apply_pantry
        total = round(sum(i["cost"] for i in apply_pantry(build_list(plan["meals"]),ctx.pantry)),2)
    else:
        total = plan_total(plan)
    if total > ctx.budget + 1e-9:
        return [f"Total cost ${total:.2f} exceeds the weekly budget of ${ctx.budget:.2f} by ${total - ctx.budget:.2f}. Choose cheaper meals or ingredients."]
    return []


def check_checkout_budget(plan,ctx):
    if not ctx.checkout_budget:return []
    from app.services.pricing import plan_checkout
    try:total,_=plan_checkout(plan['meals'],ctx.pantry,ctx.price_offers)
    except ValueError as e:return [str(e)]
    if total>ctx.budget+0.001:
        return [f"Whole-package checkout estimate ${total:.2f} exceeds the ${ctx.budget:.2f} budget. Reuse pantry ingredients, choose cheaper recipes, or update package prices."]
    return []


def check_diet(plan: dict, ctx: PlanContext) -> List[str]:
    """Every meal vs. selected restrictions/allergies AND ingredients extracted from free-text requests."""
    errors: List[str] = []
    for m in plan["meals"]:
        errors.extend(meal_violations(m, ctx.restrictions, ctx.excluded))
        errors.extend(lifestyle_violations(m,ctx))
    return errors[:15]


def schedule_for(plan: dict, ctx: PlanContext) -> Schedule:
    caps = capacities(ctx.days, ctx.prep_style, ctx.prep_days, ctx.prep_minutes, ctx.allow_pre_week)
    return schedule(plan["meals"], caps, ctx.prep_style, ctx.prep_days, [d.weekday for d in ctx.days if d.busy], earliest_day=max(ctx.earliest_day,-1 if ctx.allow_pre_week else 0), allow_freezer=ctx.allow_freezer, cooking_windows=ctx.cooking_windows, meal_times=ctx.meal_times, earliest_minute=ctx.earliest_minute)


def check_schedule(plan: dict, ctx: PlanContext) -> List[str]:
    """SOFT: can the cooking be fit into the time available, counting batches cooked on other days?"""
    return overbook_messages(schedule_for(plan, ctx))


def check_cooking_deadlines(plan: dict, ctx: PlanContext) -> List[str]:
    return deadline_errors(schedule_for(plan, ctx).sessions,ctx.cooking_windows,ctx.meal_times,ctx.earliest_day,ctx.earliest_minute)


WEEKLY_CAL_TOLERANCE = 0.10
DAILY_CAL_TOLERANCE = 0.30


def check_goal(plan: dict, ctx: PlanContext) -> List[str]:
    """SOFT: calorie target (weekly average +/-10%, each day +/-30%) and protein."""
    errors = []
    days = {}
    for m in plan["meals"]:
        d = days.setdefault(m["day"], {"cal": 0, "pro": 0.0})
        d["cal"] += m["calories"]
        d["pro"] += m["protein"]
    if not days:
        return errors
    if ctx.external_slots and ctx.goal != "none":
        return ["Nutrition totals exclude meals eaten elsewhere; full-day nutrition goals cannot be verified."]
    if 'calorie_target' in selected_goals(ctx.goal) and ctx.calorie_target:
        t = ctx.calorie_target
        avg = sum(v["cal"] for v in days.values()) / len(days)
        if abs(avg - t) > t * WEEKLY_CAL_TOLERANCE:
            errors.append(f"Average daily calories are {avg:.0f}; the target is {t} (+/-{WEEKLY_CAL_TOLERANCE:.0%} over the week).")
        for day, v in sorted(days.items()):
            if abs(v["cal"] - t) > t * DAILY_CAL_TOLERANCE:
                errors.append(f"{WEEKDAYS[day]} has {v['cal']} calories; the target is {t} (+/-{DAILY_CAL_TOLERANCE:.0%} per day).")
    target = protein_target(ctx)
    if target is not None:
        avg = sum(v["pro"] for v in days.values()) / len(days)
        if avg < target:
            errors.append(f"Average protein is {avg:.0f}g/day; your protein target is at least {target}g/day.")
        if ctx.protein_target is not None:
            for day, values in sorted(days.items()):
                if values['pro'] < target:
                    errors.append(f"{WEEKDAYS[day]} has {values['pro']:.0f}g protein; your target is at least {target}g/day.")
    return errors


def check_cost_integrity(plan: dict, ctx: PlanContext) -> List[str]:
    """Displayed per-meal cost must equal the sum of its ingredient costs (no hand-waved numbers)."""
    errors = []
    for m in plan["meals"]:
        total = round(sum(i["cost"] for i in m["ingredients"]), 2)
        if abs(total - m["cost"]) > 0.05:
            errors.append(f"'{m['name']}' reports cost ${m['cost']:.2f} but its ingredients sum to ${total:.2f}.")
    return errors[:10]


def check_pinned(plan: dict, ctx: PlanContext) -> List[str]:
    """Pinned meals must come back unchanged in the same day/slot."""
    errors = []
    at = {(m["day"], m["slot"]): m for m in plan["meals"]}
    for p in ctx.pinned:
        got = at.get((p["day"], p["slot"]))
        # Compare the normalized recipe, including amounts, nutrition and steps.
        # Coercion/defaults must match parse_plan's treatment of generated meals.
        same = got == MealIn.model_validate(p).model_dump()
        if not same:
            errors.append(f"Pinned meal '{p['name']}' ({WEEKDAYS[p['day']]} {p['slot']}) must be kept exactly as it was.")
    return errors


def check_disliked(plan: dict, ctx: PlanContext) -> List[str]:
    """Meals the user rated poorly (or just swapped away) must not come back, unless explicitly pinned."""
    pinned = {(p["day"], p["slot"]) for p in ctx.pinned}
    return [f"'{m['name']}' was rated poorly or rejected earlier; choose something else."
            for m in plan["meals"] if m["name"] in ctx.disliked and (m["day"], m["slot"]) not in pinned][:5]


# HARD: safety, money, format. A plan breaking any of these is never shown.
HARD_CHECKS = [check_coverage, check_cost_integrity, check_budget, check_checkout_budget, check_diet, check_pinned, check_disliked, check_cooking_deadlines]
# SOFT: preferences. The LLM is asked to fix them, but on the final attempt they become visible warnings.
SOFT_CHECKS = [check_schedule, check_goal]


def validate_full(raw, ctx: PlanContext):
    """Returns (normalized_plan, hard_errors, soft_warnings)."""
    plan, errors = parse_plan(raw)
    if errors:
        return plan, errors, []
    hard: List[str] = []
    for check in HARD_CHECKS:
        hard.extend(check(plan, ctx))
    soft: List[str] = []
    if not hard:
        for check in SOFT_CHECKS:
            soft.extend(check(plan, ctx))
    return plan, hard, soft


def validate_plan(raw, ctx: PlanContext):
    """Strict mode: returns (normalized_plan, errors) where errors = hard + soft. Trustworthy only when empty."""
    plan, hard, soft = validate_full(raw, ctx)
    return plan, hard + soft
