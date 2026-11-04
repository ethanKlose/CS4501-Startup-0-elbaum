"""Builds the PlanContext from the user's saved answers, asks the LLM, validates, and saves."""
import random
from dataclasses import asdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CheckIn, DaySetting, Meal, PantryItem, Plan, Profile, User
from app.services.diet import meal_violations
from app.services.explain import summarize_failure
from app.services.types import DayCtx, PlanContext
from app.services.validators import validate_plan


MAX_ATTEMPTS = 3


class PlanFailed(Exception):
    def __init__(self, message: str, errors=None, conflicts=None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []
        self.conflicts = conflicts or []


def latest_plan(db: Session, user: User) -> Optional[Plan]:
    return db.scalar(select(Plan).where(Plan.user_id == user.id).order_by(Plan.id.desc()).limit(1))


def rating_preferences(db: Session, user: User):
    """Meal names the user rated highly (avg >= 4) / poorly (avg <= 2) across all their past plans."""
    rows = db.execute(
        select(Meal.name, Meal.rating).join(Plan, Meal.plan_id == Plan.id)
        .where(Plan.user_id == user.id, Meal.rating.is_not(None))
    ).all()
    by_name: dict = {}
    for name, r in rows:
        by_name.setdefault(name, []).append(r)
    avg = {n: sum(v) / len(v) for n, v in by_name.items()}
    return sorted(n for n, a in avg.items() if a >= 4), sorted(n for n, a in avg.items() if a <= 2)


def build_context(db: Session, user: User, llm, seed: int = 0) -> PlanContext:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None or profile.budget is None:
        raise PlanFailed("Finish the survey (at least your weekly budget) before generating a plan.")
    days = {d.weekday: d for d in db.scalars(select(DaySetting).where(DaySetting.user_id == user.id))}
    checkin = db.scalar(select(CheckIn).where(CheckIn.user_id == user.id).order_by(CheckIn.id.desc()).limit(1))
    prefs_text = " . ".join(t for t in [profile.free_text, checkin.notes if checkin else ""] if t)
    interp = llm.interpret_preferences(prefs_text) if prefs_text else {"excluded": [], "day_minutes_cap": {}}
    caps = interp.get("day_minutes_cap", {})
    prev = latest_plan(db, user)
    prev_skipped = {d["weekday"] for d in (prev.days if prev and prev.status == "ok" else []) if d.get("skipped")}
    day_ctx = []
    for i in range(7):
        d = days.get(i)
        minutes = d.minutes if d else 45
        if str(i) in caps:
            minutes = min(minutes, int(caps[str(i)]))
        if checkin and checkin.cook_time == "too_much":
            minutes = int(minutes * 0.75) // 5 * 5  # last week took too long: trim every day by ~25%
        day_ctx.append(DayCtx(weekday=i, minutes=minutes, busy=bool(d and d.busy), skipped=i in prev_skipped))
    liked, disliked = rating_preferences(db, user)
    avoid = []
    if checkin and checkin.variety == "repetitive":
        names = [m.name for m in db.scalars(select(Meal).where(Meal.plan_id == checkin.plan_id))]
        avoid = sorted({n for n in names if names.count(n) >= 2})
    pinned = []
    if prev and prev.status == "ok":
        for m in prev.meals:
            d = m.as_dict()
            # keep pins only if still valid for the current diet and day plan
            if m.pinned and m.day not in prev_skipped and not meal_violations(d, profile.restrictions or [], interp.get("excluded", [])):
                pinned.append(d)
    pantry = [dict(name=p.name, quantity=p.quantity, unit=p.unit)
              for p in db.scalars(select(PantryItem).where(PantryItem.user_id == user.id))]
    return PlanContext(
        budget=profile.budget, days=day_ctx, restrictions=list(profile.restrictions or []),
        excluded=list(interp.get("excluded", [])), goal=profile.goal, calorie_target=profile.calorie_target,
        free_text=profile.free_text, pantry=pantry, pinned=pinned, liked=liked, disliked=disliked, avoid=avoid, leftovers=list(checkin.leftovers or []) if checkin else [], seed=seed,
    )


def save_plan(db: Session, user: User, ctx: PlanContext, plan_dict: dict, attempts: int) -> Plan:
    plan = Plan(user_id=user.id, status="ok", attempts=attempts, budget=ctx.budget, seed=ctx.seed,
                days=[asdict(d) for d in ctx.days])
    total = 0.0
    pinned_keys = {(p["day"], p["slot"]) for p in ctx.pinned}
    for m in sorted(plan_dict["meals"], key=lambda x: (x["day"], ["breakfast", "lunch", "dinner"].index(x["slot"]))):
        cost = round(sum(i["cost"] for i in m["ingredients"]), 2)
        total += cost
        plan.meals.append(Meal(day=m["day"], slot=m["slot"], name=m["name"], cook_minutes=m["cook_minutes"],
                               calories=m["calories"], protein=m["protein"], cost=cost,
                               steps=m["steps"], ingredients=m["ingredients"],
                               pinned=(m["day"], m["slot"]) in pinned_keys))
    plan.total_cost = round(total, 2)
    db.add(plan)
    db.flush()
    return plan


def run_with_retries(llm, ctx: PlanContext):
    """generate -> validate -> feed errors back -> retry. Returns (valid_plan_dict, attempts) or raises PlanFailed."""
    feedback: list = []
    errors: list = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = llm.generate_plan(ctx, feedback)
            plan_dict, errors = validate_plan(raw, ctx)
        except Exception as e:  # network/JSON/API errors count as a failed attempt
            plan_dict, errors = {}, [f"The generator failed: {e}"]
        if not errors:
            return plan_dict, attempt
        feedback = errors  # self-correction: the validator's complaints go straight back to the LLM
    message, conflicts = summarize_failure(ctx, errors)
    raise PlanFailed(message, errors, conflicts)


def generate(db: Session, user: User, llm, seed: Optional[int] = None) -> Plan:
    seed = random.randint(1, 10**6) if seed is None else seed
    ctx = build_context(db, user, llm, seed)
    plan_dict, attempts = run_with_retries(llm, ctx)
    plan = save_plan(db, user, ctx, plan_dict, attempts)
    db.commit()
    return plan


def swap_meal(db: Session, user: User, llm, meal: Meal) -> Meal:
    """Replace one meal. Every other meal is pinned, so only this slot changes; the WHOLE plan is re-verified."""
    plan = db.get(Plan, meal.plan_id)
    ctx = build_context(db, user, llm, random.randint(1, 10**6))
    ctx.days = [DayCtx(weekday=d["weekday"], minutes=next(c.minutes for c in ctx.days if c.weekday == d["weekday"]),
                       busy=d.get("busy", False), skipped=d.get("skipped", False)) for d in plan.days]
    ctx.pinned = [m.as_dict() for m in plan.meals if m.id != meal.id]
    ctx.disliked = list(ctx.disliked) + [meal.name]
    plan_dict, _ = run_with_retries(llm, ctx)
    new = next(m for m in plan_dict["meals"] if m["day"] == meal.day and m["slot"] == meal.slot)
    meal.name, meal.cook_minutes, meal.calories, meal.protein = new["name"], new["cook_minutes"], new["calories"], new["protein"]
    meal.steps, meal.ingredients, meal.pinned = new["steps"], new["ingredients"], False
    meal.cost = round(sum(i["cost"] for i in new["ingredients"]), 2)
    recompute_totals(plan)
    db.commit()
    return meal


def recompute_totals(plan: Plan) -> None:
    plan.total_cost = round(sum(m.cost for m in plan.meals), 2)


def set_day_skipped(db: Session, plan: Plan, weekday: int, skipped: bool) -> None:
    """Mark a day as changed (e.g. eating out). Its meals are removed, so cost and grocery list shrink."""
    days = [dict(d) for d in plan.days]  # copy: JSON columns need reassignment to register the change
    for d in days:
        if d["weekday"] == weekday:
            d["skipped"] = skipped
    plan.days = days
    if skipped:
        for m in [m for m in plan.meals if m.day == weekday]:
            plan.meals.remove(m)
    recompute_totals(plan)
    db.commit()
