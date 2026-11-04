"""Validators: no LLM-generated plan reaches the user unless validate_plan() returns [].

Each check returns a list of plain-English errors. The same strings are fed back to the LLM
on retry, and (summarized) shown to the user if retries run out.
"""
from collections import Counter
from typing import List

from app.services.diet import meal_violations
from app.services.schema import parse_plan
from app.services.types import SLOTS, WEEKDAYS, PlanContext


HIGH_PROTEIN_DAILY_G = 90


def check_coverage(plan: dict, ctx: PlanContext) -> List[str]:
    errors = []
    seen = Counter((m["day"], m["slot"]) for m in plan["meals"])
    for d in ctx.days:
        for slot in SLOTS:
            n = seen.get((d.weekday, slot), 0)
            if d.skipped and n:
                errors.append(f"{WEEKDAYS[d.weekday]} is marked as skipped; remove its meals.")
                break
            if not d.skipped and n == 0:
                errors.append(f"Missing {slot} on {WEEKDAYS[d.weekday]}.")
            if n > 1:
                errors.append(f"More than one {slot} on {WEEKDAYS[d.weekday]}.")
    return errors


def plan_total(plan: dict) -> float:
    """Total recomputed from ingredient costs - never trust the LLM's own arithmetic."""
    return round(sum(i["cost"] for m in plan["meals"] for i in m["ingredients"]), 2)


def check_budget(plan: dict, ctx: PlanContext) -> List[str]:
    total = plan_total(plan)
    if total > ctx.budget + 1e-9:
        return [f"Total cost ${total:.2f} exceeds the weekly budget of ${ctx.budget:.2f} by ${total - ctx.budget:.2f}. Choose cheaper meals or ingredients."]
    return []


def check_diet(plan: dict, ctx: PlanContext) -> List[str]:
    """Every meal vs. selected restrictions/allergies AND ingredients extracted from free-text requests."""
    errors: List[str] = []
    for m in plan["meals"]:
        errors.extend(meal_violations(m, ctx.restrictions, ctx.excluded))
    return errors[:15]


def check_time(plan: dict, ctx: PlanContext) -> List[str]:
    errors = []
    by_day = Counter()
    for m in plan["meals"]:
        by_day[m["day"]] += m["cook_minutes"]
    for d in ctx.days:
        if by_day[d.weekday] > d.minutes:
            errors.append(f"{WEEKDAYS[d.weekday]} needs {by_day[d.weekday]} cooking minutes but only {d.minutes} are available.")
    return errors


def check_goal(plan: dict, ctx: PlanContext) -> List[str]:
    errors = []
    days = {}
    for m in plan["meals"]:
        d = days.setdefault(m["day"], {"cal": 0, "pro": 0.0})
        d["cal"] += m["calories"]
        d["pro"] += m["protein"]
    if not days:
        return errors
    if ctx.goal == "calorie_target" and ctx.calorie_target:
        lo, hi = ctx.calorie_target * 0.8, ctx.calorie_target * 1.2
        for day, v in sorted(days.items()):
            if not lo <= v["cal"] <= hi:
                errors.append(f"{WEEKDAYS[day]} has {v['cal']} calories; the target is {ctx.calorie_target} (+/-20%).")
    if ctx.goal == "high_protein":
        avg = sum(v["pro"] for v in days.values()) / len(days)
        if avg < HIGH_PROTEIN_DAILY_G:
            errors.append(f"Average protein is {avg:.0f}g/day; a high-protein goal needs at least {HIGH_PROTEIN_DAILY_G}g/day.")
    return errors


CHECKS = [check_coverage, check_time, check_budget, check_diet, check_goal]


def validate_plan(raw, ctx: PlanContext):
    """Returns (normalized_plan, errors). Plan is only trustworthy when errors == []."""
    plan, errors = parse_plan(raw)
    if errors:
        return plan, errors
    for check in CHECKS:
        errors.extend(check(plan, ctx))
    return plan, errors
