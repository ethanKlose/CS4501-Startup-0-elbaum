from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import DaySetting, Profile, User

router = APIRouter()

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
RESTRICTIONS = {
    "vegetarian": "Vegetarian",
    "vegan": "Vegan",
    "gluten_free": "Gluten-free",
    "dairy_free": "Dairy-free",
    "nut_allergy": "Nut allergy",
    "shellfish_allergy": "Shellfish allergy",
    "egg_free": "Egg-free",
    "halal": "Halal",
}
GOALS = {"none": "No specific goal", "high_protein": "High protein", "calorie_target": "Daily calorie target"}
DEFAULT_MINUTES = 45
MAX_MINUTES = 480


def get_profile(db: Session, user: User) -> Profile:
    p = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if p is None:
        p = Profile(user_id=user.id)
        db.add(p)
        db.flush()
    return p


def get_days(db: Session, user: User) -> List[DaySetting]:
    """Always returns 7 rows (creating defaults), ordered Monday..Sunday."""
    rows = {d.weekday: d for d in db.scalars(select(DaySetting).where(DaySetting.user_id == user.id))}
    for i in range(7):
        if i not in rows:
            rows[i] = DaySetting(user_id=user.id, weekday=i, busy=False, minutes=DEFAULT_MINUTES)
            db.add(rows[i])
    db.flush()
    return [rows[i] for i in range(7)]


def parse_budget(raw: str):
    """Return (value, error). Rejects empty, non-numeric, zero, negative."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None, "Enter your weekly grocery budget as a number."
    if v != v or v <= 0:
        return None, "Budget must be greater than zero."
    if v > 10000:
        return None, "Budget looks too large — enter a weekly amount."
    return round(v, 2), None


def parse_minutes(raw: str):
    try:
        v = int(float(raw))
    except (TypeError, ValueError):
        return None
    return v if 0 <= v <= MAX_MINUTES else None


# ---- section appliers: (form, profile, errors, db, user) -> None -----------------------------

def apply_budget(form, profile, errors, **_):
    if "budget" not in form:
        return
    value, err = parse_budget(form.get("budget", ""))
    if err:
        errors["budget"] = err
    else:
        profile.budget = value


def apply_days(form, errors, db, user, **_):
    if not any(k.startswith("minutes_") for k in form.keys()):
        return
    for d in get_days(db, user):
        m = parse_minutes(form.get(f"minutes_{d.weekday}", str(DEFAULT_MINUTES)))
        if m is None:
            errors[f"minutes_{d.weekday}"] = f"{WEEKDAYS[d.weekday]}: enter minutes between 0 and {MAX_MINUTES}."
            continue
        d.minutes = m
        d.busy = form.get(f"busy_{d.weekday}") is not None


def apply_restrictions(form, profile, **_):
    # Hidden marker field tells us the section was actually on the submitted form.
    if "restrictions_present" not in form:
        return
    chosen = [r for r in form.getlist("restrictions") if r in RESTRICTIONS]
    profile.restrictions = sorted(set(chosen))


def apply_goal(form, profile, errors, **_):
    if "goal" not in form:
        return
    goal = form.get("goal", "none")
    if goal not in GOALS:
        errors["goal"] = "Pick a goal from the list."
        return
    profile.goal = goal
    profile.calorie_target = None
    if goal == "calorie_target":
        try:
            cal = int(float(form.get("calorie_target", "")))
        except ValueError:
            cal = 0
        if not 800 <= cal <= 6000:
            errors["goal"] = "Enter a daily calorie target between 800 and 6000."
            return
        profile.calorie_target = cal


MAX_FREE_TEXT = 500


def apply_free_text(form, profile, errors, **_):
    if "free_text" not in form:
        return
    text = form.get("free_text", "").strip()
    if len(text) > MAX_FREE_TEXT:
        errors["free_text"] = f"Keep extra preferences under {MAX_FREE_TEXT} characters."
        return
    profile.free_text = text


APPLIERS = [apply_budget, apply_days, apply_restrictions, apply_goal, apply_free_text]


@router.get("/survey")
def survey_form(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = survey_context(db, user)
    db.commit()
    return render(request, "survey.html", user, errors={}, saved=request.query_params.get("saved"), **ctx)


def survey_context(db, user):
    return dict(profile=get_profile(db, user), days=get_days(db, user), weekdays=WEEKDAYS, restriction_options=RESTRICTIONS, goal_options=GOALS)


@router.post("/survey")
async def survey_submit(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = await request.form()
    profile = get_profile(db, user)
    errors: Dict[str, str] = {}
    for fn in APPLIERS:
        fn(form=form, profile=profile, errors=errors, db=db, user=user)
    if errors:
        db.rollback()
        ctx = survey_context(db, user)
        db.rollback()
        return render(request, "survey.html", user, 400, errors=errors, form=dict(form), form_restrictions=form.getlist("restrictions"), **ctx)
    db.commit()
    return RedirectResponse("/survey?saved=1", 303)
