"""Validators: no LLM-generated plan reaches the user unless validate_plan() returns [].

Each check returns a list of plain-English errors. The same strings are fed back to the LLM
on retry, and (summarized) shown to the user if retries run out.
"""
from collections import Counter
from typing import List

from app.services.schema import parse_plan
from app.services.types import SLOTS, WEEKDAYS, PlanContext


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


CHECKS = [check_coverage]


def validate_plan(raw, ctx: PlanContext):
    """Returns (normalized_plan, errors). Plan is only trustworthy when errors == []."""
    plan, errors = parse_plan(raw)
    if errors:
        return plan, errors
    for check in CHECKS:
        errors.extend(check(plan, ctx))
    return plan, errors
