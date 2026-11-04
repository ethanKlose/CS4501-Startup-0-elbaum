"""When no valid plan can be produced, work out WHICH constraints conflict and what to change.

Uses the recipe catalog as the feasibility reference: it tells us the cheapest/quickest/closest-to-goal
meals possible under the user's restrictions, independent of whichever LLM failed.
"""
import itertools
from typing import List

from app.services.catalog import RECIPES
from app.services.diet import meal_violations
from app.services.types import SLOTS, WEEKDAYS, PlanContext
from app.services.validators import HIGH_PROTEIN_DAILY_G


def find_conflicts(ctx: PlanContext) -> List[str]:
    out: List[str] = []
    allowed = [r for r in RECIPES if not meal_violations(r, ctx.restrictions, ctx.excluded)]
    by_slot = {s: [r for r in allowed if s in r["slots"]] for s in SLOTS}
    labels = ", ".join([x.replace("_", " ") for x in ctx.restrictions] + [f"'{e}'" for e in ctx.excluded])

    empty = [s for s in SLOTS if not by_slot[s]]
    if empty:
        out.append(f"Your restrictions and preferences ({labels}) leave no {'/'.join(empty)} options. "
                   f"Remove or relax one of them.")
        return out

    active = ctx.active_days()
    if not active:
        return ["Every day is marked as skipped, so there is nothing to plan."]

    # budget
    min_week = round(sum(min(r["cost"] for r in by_slot[s]) for _ in active for s in SLOTS), 2)
    if min_week > ctx.budget:
        out.append(f"Your budget (${ctx.budget:.2f}) is too low: the cheapest week that fits your restrictions "
                   f"costs about ${min_week:.2f}. Raise your budget to at least ${min_week:.0f}, or relax a restriction.")

    # time
    for d in active:
        need = sum(min(r["cook_minutes"] for r in by_slot[s]) for s in SLOTS)
        if need > d.minutes:
            out.append(f"{WEEKDAYS[d.weekday]}: you have {d.minutes} cooking minutes but the quickest allowed meals "
                       f"need {need}. Add time on {WEEKDAYS[d.weekday]} or mark it as eating out.")

    # goal
    if ctx.goal in ("calorie_target", "high_protein") and active:
        best_cal, best_pro, lo_cal = {}, {}, {}
        for d in active:
            feasible = [c for c in itertools.product(*[by_slot[s] for s in SLOTS]) if sum(r["cook_minutes"] for r in c) <= d.minutes]
            if not feasible:
                continue
            best_cal[d.weekday] = max(sum(r["calories"] for r in c) for c in feasible)
            lo_cal[d.weekday] = min(sum(r["calories"] for r in c) for c in feasible)
            best_pro[d.weekday] = max(sum(r["protein"] for r in c) for c in feasible)
        if ctx.calorie_target and best_cal:
            hi, lo = max(best_cal.values()), min(lo_cal.values())
            if hi < ctx.calorie_target * 0.8:
                out.append(f"A {ctx.calorie_target}-calorie day isn't reachable with your restrictions and cooking time "
                           f"(the most we can fit is about {hi}). Lower the target or add cooking time.")
            elif lo > ctx.calorie_target * 1.2:
                out.append(f"A {ctx.calorie_target}-calorie target is below what we can build (minimum about {lo}/day). Raise the target.")
        if ctx.goal == "high_protein" and best_pro and sum(best_pro.values()) / len(best_pro) < HIGH_PROTEIN_DAILY_G:
            out.append("A high-protein goal isn't reachable with your restrictions and cooking time. "
                       "Add cooking time, relax a restriction, or drop the goal.")
    return out


def summarize_failure(ctx: PlanContext, errors: List[str]):
    """Returns (message, conflicts)."""
    conflicts = find_conflicts(ctx)
    if conflicts:
        return "We couldn't build a plan that meets all your constraints. Here's what to adjust:", conflicts
    return ("We couldn't produce a plan that passed every check. Try regenerating, or relax a constraint.",
            [e for e in errors[:3]])
