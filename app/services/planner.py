"""Builds the PlanContext from the user's saved answers, asks the LLM, validates, and saves."""
import random
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DaySetting, Meal, PantryItem, Plan, Profile, User
from app.services.types import DayCtx, PlanContext
from app.services.validators import validate_plan


class PlanFailed(Exception):
    def __init__(self, message: str, errors=None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


def latest_plan(db: Session, user: User) -> Optional[Plan]:
    return db.scalar(select(Plan).where(Plan.user_id == user.id).order_by(Plan.id.desc()).limit(1))


def build_context(db: Session, user: User, llm, seed: int = 0) -> PlanContext:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None or profile.budget is None:
        raise PlanFailed("Finish the survey (at least your weekly budget) before generating a plan.")
    days = {d.weekday: d for d in db.scalars(select(DaySetting).where(DaySetting.user_id == user.id))}
    interp = llm.interpret_preferences(profile.free_text) if profile.free_text else {"excluded": [], "day_minutes_cap": {}}
    caps = interp.get("day_minutes_cap", {})
    day_ctx = []
    for i in range(7):
        d = days.get(i)
        minutes = d.minutes if d else 45
        if str(i) in caps:
            minutes = min(minutes, int(caps[str(i)]))
        day_ctx.append(DayCtx(weekday=i, minutes=minutes, busy=bool(d and d.busy)))
    pantry = [dict(name=p.name, quantity=p.quantity, unit=p.unit)
              for p in db.scalars(select(PantryItem).where(PantryItem.user_id == user.id))]
    return PlanContext(
        budget=profile.budget, days=day_ctx, restrictions=list(profile.restrictions or []),
        excluded=list(interp.get("excluded", [])), goal=profile.goal, calorie_target=profile.calorie_target,
        free_text=profile.free_text, pantry=pantry, seed=seed,
    )


def save_plan(db: Session, user: User, ctx: PlanContext, plan_dict: dict, attempts: int) -> Plan:
    plan = Plan(user_id=user.id, status="ok", attempts=attempts, budget=ctx.budget, seed=ctx.seed)
    total = 0.0
    for m in sorted(plan_dict["meals"], key=lambda x: (x["day"], ["breakfast", "lunch", "dinner"].index(x["slot"]))):
        cost = round(sum(i["cost"] for i in m["ingredients"]), 2)
        total += cost
        plan.meals.append(Meal(day=m["day"], slot=m["slot"], name=m["name"], cook_minutes=m["cook_minutes"],
                               calories=m["calories"], protein=m["protein"], cost=cost,
                               steps=m["steps"], ingredients=m["ingredients"]))
    plan.total_cost = round(total, 2)
    db.add(plan)
    db.flush()
    return plan


def generate(db: Session, user: User, llm, seed: Optional[int] = None) -> Plan:
    seed = random.randint(1, 10**6) if seed is None else seed
    ctx = build_context(db, user, llm, seed)
    raw = llm.generate_plan(ctx, [])
    plan_dict, errors = validate_plan(raw, ctx)
    if errors:
        raise PlanFailed("We couldn't build a valid plan: " + " ".join(errors[:3]), errors)
    plan = save_plan(db, user, ctx, plan_dict, 1)
    db.commit()
    return plan
