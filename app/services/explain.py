"""When no valid plan can be produced, work out WHICH constraints conflict and what to change.

Only HARD constraints can make generation fail (diet/allergies, budget, format, pins). Time and goal
shortfalls are SOFT: they produce warnings on a finished plan instead. This module uses the recipe
catalog as the feasibility reference, independent of whichever LLM failed.
"""
from typing import List

from app.services.catalog import RECIPES
from app.services.diet import meal_violations
from app.services.types import SLOTS, PlanContext


def find_conflicts(ctx: PlanContext) -> List[str]:
    out: List[str] = []
    from app.services.lifestyle import violations
    from app.services.pricing import apply_recipe_prices
    allowed = [apply_recipe_prices(r,ctx.price_offers) for r in RECIPES if not meal_violations(r, ctx.restrictions, ctx.excluded) and r["name"] not in ctx.disliked and not violations(r,ctx)]
    by_slot = {s: [r for r in allowed if s in r["slots"]] for s in SLOTS}
    labels = ", ".join([x.replace("_", " ") for x in ctx.restrictions] + [f"'{e}'" for e in ctx.excluded])

    required = [(d.weekday,s) for d in ctx.active_days() for s in ctx.slots_for(d.weekday)]
    empty = [s for s in SLOTS if any(slot == s for _,slot in required) and not by_slot[s]]
    if empty:
        out.append(f"Your restrictions and preferences ({labels or 'including rated-down meals'}) leave no {'/'.join(empty)} options. "
                   f"Remove or relax one of them.")
        return out

    active = ctx.active_days()
    if not active:
        return ["Every day is marked as skipped, so there is nothing to plan."]

    min_week = round(sum(min(r["cost"] for r in by_slot[s]) for _,s in required), 2)
    if (not ctx.checkout_budget or not ctx.pantry) and min_week > ctx.budget + .05:
        out.append(f"Your budget (${ctx.budget:.2f}) is too low: the cheapest catalog recipe portions that fit your restrictions "
                   f"costs about ${min_week:.2f}. Raise your budget to at least ${min_week:.0f}, or relax a restriction.")

    pinned_cost = sum(p["cost"] for p in ctx.pinned)
    if not ctx.checkout_budget and pinned_cost > ctx.budget:
        out.append(f"Your pinned meals alone cost ${pinned_cost:.2f}, over your ${ctx.budget:.2f} budget. Unpin some or raise the budget.")
    return out


def summarize_failure(ctx: PlanContext, errors: List[str]):
    """Returns (message, conflicts)."""
    conflicts = find_conflicts(ctx)
    if conflicts:
        return "We couldn't build a plan that meets all your constraints. Here's what to adjust:", conflicts
    return ("The search did not find a plan that passed every check. This does not prove your constraints are impossible. Try regenerating or adjusting your choices.",
            [e for e in errors[:3]])
