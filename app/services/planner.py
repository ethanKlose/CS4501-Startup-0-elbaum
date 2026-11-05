"""Builds the PlanContext from the user's saved answers, asks the LLM, validates, and saves."""
import random
import time
import datetime as dt
from dataclasses import asdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CheckIn, DaySetting, Meal, PantryItem, Plan, Profile, User
from app.services.diet import meal_violations
from app.services.explain import summarize_failure
from app.services.schedule import capacities, schedule
from app.services.types import DayCtx, PlanContext
from app.services import inventory
from app.services.locking import lock_user
from app.services.preferences import get_preferences
from app.services.weeks import plan_week_start, planning_today, planning_now, target_week
from app.services.validators import SOFT_CHECKS, schedule_for, validate_full


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


def build_context(db: Session, user: User, llm, seed: int = 0, week_start=None) -> PlanContext:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None or profile.budget is None:
        raise PlanFailed("Finish the survey (at least your weekly budget) before generating a plan.")
    days = {d.weekday: d for d in db.scalars(select(DaySetting).where(DaySetting.user_id == user.id))}
    checkin = db.scalar(select(CheckIn).where(CheckIn.user_id == user.id).order_by(CheckIn.id.desc()).limit(1))
    prefs_text = " . ".join(t for t in [profile.free_text, checkin.notes if checkin else ""] if t)
    interp = llm.interpret_preferences(prefs_text) if prefs_text else {"excluded": [], "day_minutes_cap": {}}
    caps = interp.get("day_minutes_cap", {})
    prev = latest_plan(db, user)
    week_start = week_start or target_week(prev)
    same_week = prev and plan_week_start(prev) == week_start
    prev_skipped = {d["weekday"] for d in (prev.days if same_week and prev.status == "ok" else []) if d.get("skipped")}
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
    if same_week and prev.status == "ok":
        for m in prev.meals:
            d = m.as_dict()
            # keep pins only if still valid for the current diet and day plan
            if m.pinned and m.day not in prev_skipped and not meal_violations(d, profile.restrictions or [], interp.get("excluded", [])):
                pinned.append(d)
    lifestyle = get_preferences(db,user.id)
    now=planning_now()
    earliest_day=-1
    earliest_minute=0
    external_slots=list(lifestyle.get('external_slots',[]))
    if week_start<=planning_today()<week_start+dt.timedelta(days=7):
        earliest_day=(planning_today()-week_start).days
        earliest_minute=now.hour*60+now.minute+1
        for day in day_ctx:
            if day.weekday<earliest_day:day.skipped=True
        from app.services.timing import EAT
        for slot,(default,_) in EAT.items():
            if lifestyle.get('meal_times',{}).get(slot,default)<earliest_minute:
                external_slots.append({'day':earliest_day,'slot':slot,'source':'Before planning start','past':True})
    if lifestyle.get('equipment') is not None and 'fridge' not in lifestyle['equipment']:
        profile_prep_style='daily'
    else:profile_prep_style=profile.prep_style or 'auto'
    pantry = [dict(name=p.name, quantity=p.quantity, unit=p.unit)
              for p in db.scalars(select(PantryItem).where(PantryItem.user_id == user.id))]
    inactive={(m['day'],m['slot']) for m in external_slots}
    active_days={d.weekday for d in day_ctx if not d.skipped}
    pinned=[p for p in pinned if p['day'] in active_days and (p['day'],p['slot']) not in inactive]
    return PlanContext(
        budget=profile.budget, days=day_ctx,
        preference_warnings=list(interp.get('warnings',[])),
        price_offers=dict(lifestyle.get('price_offers',{})), checkout_budget=True, equipment=lifestyle.get('equipment'), cooking_skill=lifestyle.get('cooking_skill','any'),
        allow_freezer='freezer' in lifestyle.get('equipment',['freezer']),
        external_slots=external_slots, earliest_day=earliest_day, earliest_minute=earliest_minute, cooking_windows=dict(lifestyle.get('cooking_windows',{})),
        meal_times=dict(lifestyle.get('meal_times',{})), restrictions=list(profile.restrictions or []),
        excluded=list(interp.get("excluded", [])), goal=profile.goal, calorie_target=profile.calorie_target,
        free_text=profile.free_text, pantry=pantry, pinned=pinned, liked=liked, disliked=disliked, avoid=avoid, leftovers=list(checkin.leftovers or []) if checkin else [],
        week_start=week_start.isoformat(), allow_pre_week=(week_start - dt.timedelta(days=1)) > planning_today(),
        prep_style=profile_prep_style, prep_days=list(profile.prep_days or []), prep_minutes=profile.prep_minutes or 120, seed=seed,
    )


def plan_settings(ctx: PlanContext) -> dict:
    return dict(restrictions=list(ctx.restrictions),excluded=list(ctx.excluded),pantry=list(ctx.pantry),preference_warnings=list(ctx.preference_warnings),prep_style=ctx.prep_style, prep_days=list(ctx.prep_days), prep_minutes=ctx.prep_minutes,
                goal=ctx.goal, calorie_target=ctx.calorie_target, equipment=ctx.equipment, cooking_skill=ctx.cooking_skill,
                allow_freezer=ctx.allow_freezer, price_offers=ctx.price_offers, checkout_budget=ctx.checkout_budget, earliest_day=ctx.earliest_day, earliest_minute=ctx.earliest_minute, external_slots=ctx.external_slots, cooking_windows=ctx.cooking_windows, meal_times=ctx.meal_times, week_start=ctx.week_start, allow_pre_week=ctx.allow_pre_week)


def save_plan(db: Session, user: User, ctx: PlanContext, plan_dict: dict, attempts: int, warnings=()) -> Plan:
    plan = Plan(user_id=user.id, status="ok", attempts=attempts, budget=ctx.budget, seed=ctx.seed,
                days=[asdict(d) for d in ctx.days], settings=plan_settings(ctx), warnings=list(warnings))
    sched = schedule_for(plan_dict, ctx)
    total = 0.0
    pinned_keys = {(p["day"], p["slot"]) for p in ctx.pinned}
    for m in sorted(plan_dict["meals"], key=lambda x: (x["day"], ["breakfast", "lunch", "dinner"].index(x["slot"]))):
        cost = round(sum(i["cost"] for i in m["ingredients"]), 2)
        total += cost
        cook_day, frozen = sched.assign[(m["day"], m["slot"])]
        plan.meals.append(Meal(day=m["day"], slot=m["slot"], name=m["name"], cook_minutes=m["cook_minutes"],
                               calories=m["calories"], protein=m["protein"], cost=cost,
                               steps=m["steps"], ingredients=m["ingredients"],
                               pinned=(m["day"], m["slot"]) in pinned_keys, cook_day=cook_day, frozen=frozen))
    plan.total_cost = round(total, 2)
    from app.services.pricing import plan_checkout
    checkout_total,_=plan_checkout(plan_dict['meals'],ctx.pantry,ctx.price_offers)
    plan.settings=dict(plan.settings,checkout_total=checkout_total)
    db.add(plan)
    db.flush()
    return plan


def plan_ctx(plan: Plan) -> PlanContext:
    """Rebuild a lightweight context from what was saved with the plan (no LLM or DB lookups)."""
    st = plan.settings or {}
    return PlanContext(budget=plan.budget, days=[DayCtx(d["weekday"], d["minutes"], d.get("busy", False), d.get("skipped", False)) for d in plan.days],
                       restrictions=st.get('restrictions',[]),excluded=st.get('excluded',[]),pantry=st.get('pantry',[]),preference_warnings=st.get('preference_warnings',[]),
                       goal=st.get("goal", "none"), calorie_target=st.get("calorie_target"), prep_style=st.get("prep_style", "auto"),
                       prep_days=st.get("prep_days", []), prep_minutes=st.get("prep_minutes", 120),
                       price_offers=st.get('price_offers',{}), checkout_budget=st.get('checkout_budget',False), equipment=st.get('equipment'), cooking_skill=st.get('cooking_skill','any'), allow_freezer=st.get('allow_freezer',True),
                       earliest_day=st.get('earliest_day',-1), earliest_minute=st.get('earliest_minute',0), external_slots=st.get('external_slots',[]), cooking_windows=st.get('cooking_windows',{}), meal_times=st.get('meal_times',{}),
                       week_start=st.get("week_start"), allow_pre_week=st.get("allow_pre_week", True))


def reschedule(plan: Plan) -> None:
    """Recompute cook days and soft warnings after the meals changed (swap, skipped day)."""
    ctx = plan_ctx(plan)
    pd = dict(meals=[m.as_dict() for m in plan.meals])
    sched = schedule_for(pd, ctx)
    for m in plan.meals:
        m.cook_day, m.frozen = sched.assign[(m.day, m.slot)]
    plan.warnings = ([w for check in SOFT_CHECKS for w in check(pd, ctx)] if pd["meals"] else []) + list(ctx.preference_warnings)


def run_with_retries(llm, ctx: PlanContext):
    """generate -> validate -> feed errors back -> retry.

    Attempts 1..N-1 are strict: hard AND soft issues go back to the LLM. The final attempt is tolerant:
    a plan with only soft issues (e.g. a rest day below the calorie target) is accepted with warnings.
    Returns (plan_dict, attempts, warnings) or raises PlanFailed.
    """
    feedback: list = []
    errors: list = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started=time.perf_counter()
        try:
            raw = llm.generate_plan(ctx, feedback)
            plan_dict, hard, soft = validate_full(raw, ctx)
        except Exception as e:  # network/JSON/API errors count as a failed attempt
            plan_dict, hard, soft = {}, [f"The generator failed: {e}"], []
        ctx.generation_trace.append(dict(attempt=attempt,seconds=round(time.perf_counter()-started,3),hard_errors=list(hard),soft_warnings=list(soft)))
        if not hard and not soft:
            return plan_dict, attempt, list(ctx.preference_warnings)
        if not hard and attempt == MAX_ATTEMPTS:
            return plan_dict, attempt, soft + list(ctx.preference_warnings)
        errors = hard + soft
        feedback = errors  # self-correction: the validator's complaints go straight back to the LLM
    message, conflicts = summarize_failure(ctx, errors)
    raise PlanFailed(message, errors, conflicts)


def generate(db: Session, user: User, llm, seed: Optional[int] = None, new_week: bool = False, start_mode: str = "keep") -> Plan:
    lock_user(db, user.id)
    seed = random.randint(1, 10**6) if seed is None else seed
    previous = latest_plan(db, user)
    if previous:
        inventory.settle(db, previous)
    week=target_week(latest_plan(db,user),new_week)
    if start_mode=='today':week=planning_today()-dt.timedelta(days=planning_today().weekday())
    elif start_mode=='next_week':
        from app.services.weeks import next_monday
        week=next_monday(planning_today())
    ctx = build_context(db, user, llm, seed, week_start=week)
    plan_dict, attempts, warnings = run_with_retries(llm, ctx)
    plan = save_plan(db, user, ctx, plan_dict, attempts, warnings)
    plan.settings=dict(plan.settings,generation={'engine':getattr(llm,'name','custom'),'attempts':attempts,'trace':ctx.generation_trace,'api_calls':list(getattr(llm,'metrics',[]))})
    db.commit()
    return plan


def swap_meal(db: Session, user: User, llm, meal: Meal) -> Meal:
    """Replace one meal. Every other meal is pinned, so only this slot changes; the WHOLE plan is re-verified."""
    if inventory.closed(db.get(Plan, meal.plan_id)):
        raise PlanFailed("This plan is closed. Generate a new week to make changes.")
    if meal.status != "planned" or meal.rating is not None:
        raise PlanFailed("Only planned, unrated meals can be swapped. Completed meals keep their cooking and rating history.")
    plan = db.get(Plan, meal.plan_id)
    ctx = build_context(db, user, llm, random.randint(1, 10**6), week_start=plan_week_start(plan))
    ctx.days = [DayCtx(weekday=d["weekday"], minutes=next(c.minutes for c in ctx.days if c.weekday == d["weekday"]),
                       busy=d.get("busy", False), skipped=d.get("skipped", False)) for d in plan.days]
    ctx.pinned = [m.as_dict() for m in plan.meals if m.id != meal.id]
    ctx.disliked = list(ctx.disliked) + [meal.name]
    plan_dict, _, _ = run_with_retries(llm, ctx)
    new = next(m for m in plan_dict["meals"] if m["day"] == meal.day and m["slot"] == meal.slot)
    meal.name, meal.cook_minutes, meal.calories, meal.protein = new["name"], new["cook_minutes"], new["calories"], new["protein"]
    meal.steps, meal.ingredients, meal.pinned = new["steps"], new["ingredients"], False
    meal.cost = round(sum(i["cost"] for i in new["ingredients"]), 2)
    plan.budget = ctx.budget
    plan.days = [asdict(d) for d in ctx.days]
    plan.settings = dict(plan.settings or {}, **plan_settings(ctx))
    recompute_totals(plan)
    reschedule(plan)
    db.commit()
    return meal


def recompute_totals(plan: Plan) -> None:
    plan.total_cost = round(sum(m.cost for m in plan.meals), 2)


def set_day_skipped(db: Session, plan: Plan, weekday: int, skipped: bool) -> None:
    """Mark a day as changed (e.g. eating out). Its meals are removed, so cost and grocery list shrink."""
    if inventory.closed(plan):
        raise PlanFailed("This plan is closed. Generate a new week to make changes.")
    if skipped and any(m.day == weekday and (m.status == "cooked" or m.rating is not None) for m in plan.meals):
        raise PlanFailed("A day with completed meals cannot be removed. Its cooking and rating history is kept.")
    days = [dict(d) for d in plan.days]  # copy: JSON columns need reassignment to register the change
    for d in days:
        if d["weekday"] == weekday:
            d["skipped"] = skipped
    plan.days = days
    if skipped:
        for m in [m for m in plan.meals if m.day == weekday]:
            plan.meals.remove(m)
    recompute_totals(plan)
    reschedule(plan)
    db.commit()
