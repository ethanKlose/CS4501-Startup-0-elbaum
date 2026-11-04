from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.services.llm import get_llm
from app.services.schedule import PREP_STYLES
from app.models import DaySetting, PantryItem, Profile, User

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
MIN_BUDGET = 30
MIN_CALORIES, MAX_CALORIES = 1200, 4500
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
    if v < MIN_BUDGET:
        return None, f"Budget must be at least ${MIN_BUDGET} a week to cover three meals a day."
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
        if not MIN_CALORIES <= cal <= MAX_CALORIES:
            errors["goal"] = f"Enter a daily calorie target between {MIN_CALORIES} and {MAX_CALORIES}."
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


def apply_prep(form, profile, errors, **_):
    if "prep_present" not in form:
        return
    style = form.get("prep_style", "auto")
    if style not in PREP_STYLES:
        errors["prep"] = "Pick a cooking style from the list."
        return
    try:
        minutes = int(float(form.get("prep_minutes", "120")))
    except ValueError:
        minutes = 0
    if not 30 <= minutes <= MAX_MINUTES:
        errors["prep"] = f"A cooking session should be between 30 and {MAX_MINUTES} minutes."
        return
    profile.prep_style = style
    profile.prep_minutes = minutes
    profile.prep_days = sorted({int(d) for d in form.getlist("prep_days") if d.isdigit() and 0 <= int(d) <= 6})


APPLIERS = [apply_budget, apply_days, apply_restrictions, apply_goal, apply_free_text, apply_prep]


@router.get("/survey")
def survey_form(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = survey_context(db, user)
    values = field_values(ctx["profile"], ctx["days"])
    db.commit()
    return render(request, "survey.html", user, errors={}, values=values, saved=request.query_params.get("saved"), pantry_error=request.query_params.get("pantry_error"), **ctx)


def understood(profile: Profile, days) -> List[str]:
    """Plain-English readback of how we interpreted the answers, so surprises are visible before generating."""
    out = []
    if profile.restrictions:
        out.append("Diet: " + ", ".join(RESTRICTIONS[r] for r in profile.restrictions if r in RESTRICTIONS))
    interp = profile.interpreted or {}
    if interp.get("excluded"):
        out.append("Never serving (from your note): " + ", ".join(interp["excluded"]))
    caps = {int(k): v for k, v in (interp.get("day_minutes_cap") or {}).items()}
    effective = {}
    for d in days:
        effective[d.weekday] = min(d.minutes, caps[d.weekday]) if d.weekday in caps else d.minutes
    for wd, cap in sorted(caps.items()):
        out.append(f"{WEEKDAYS[wd]}: cooking limited to {cap} min (from your note)")
    none = [WEEKDAYS[w][:3] for w, m in sorted(effective.items()) if m == 0]
    if none:
        out.append("No cooking on " + ", ".join(none) + ". Those days' meals will be cooked on another day and reheated.")
    style = PREP_STYLES.get(profile.prep_style or "auto", "")
    extra = f", preferring {', '.join(WEEKDAYS[d][:3] for d in profile.prep_days)} ({profile.prep_minutes} min sessions)" if profile.prep_days else ""
    out.append(f"Cooking style: {style}{extra}")
    if profile.goal == "high_protein":
        out.append("Goal: high protein")
    elif profile.goal == "calorie_target" and profile.calorie_target:
        out.append(f"Goal: about {profile.calorie_target} calories a day")
    return out


def field_values(profile: Profile, days, form=None) -> dict:
    """What every input should show: the saved answers, or (after a rejected submit) what the user just typed."""
    if form is None:
        return dict(
            budget=profile.budget if profile.budget is not None else "", goal=profile.goal or "none",
            calorie_target=profile.calorie_target or "", free_text=profile.free_text or "",
            restrictions=list(profile.restrictions or []), prep_style=profile.prep_style or "auto",
            prep_days=[str(d) for d in (profile.prep_days or [])], prep_minutes=profile.prep_minutes or 120,
            days=[dict(weekday=d.weekday, busy=d.busy, minutes=d.minutes) for d in days])
    return dict(
        budget=form.get("budget", ""), goal=form.get("goal", profile.goal or "none"), calorie_target=form.get("calorie_target", ""),
        free_text=form.get("free_text", ""), restrictions=form.getlist("restrictions"),
        prep_style=form.get("prep_style", profile.prep_style or "auto"), prep_days=form.getlist("prep_days"),
        prep_minutes=form.get("prep_minutes", profile.prep_minutes or 120),
        days=[dict(weekday=d.weekday, busy=form.get(f"busy_{d.weekday}") is not None, minutes=form.get(f"minutes_{d.weekday}", d.minutes)) for d in days])


def survey_context(db, user):
    pantry = list(db.scalars(select(PantryItem).where(PantryItem.user_id == user.id).order_by(PantryItem.name)))
    profile, days = get_profile(db, user), get_days(db, user)
    return dict(pantry=pantry, profile=profile, days=days, understood=understood(profile, days), weekdays=WEEKDAYS, restriction_options=RESTRICTIONS, goal_options=GOALS, prep_styles=PREP_STYLES)


@router.post("/survey")
async def survey_submit(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), llm=Depends(get_llm)):
    form = await request.form()
    profile = get_profile(db, user)
    errors: Dict[str, str] = {}
    for fn in APPLIERS:
        fn(form=form, profile=profile, errors=errors, db=db, user=user)
    if errors:
        db.rollback()
        ctx = survey_context(db, user)
        db.rollback()
        return render(request, "survey.html", user, 400, errors=errors, values=field_values(ctx["profile"], ctx["days"], form), **ctx)
    if "free_text" in form:  # remember how the note was understood, to show it back to the user
        try:
            profile.interpreted = llm.interpret_preferences(profile.free_text) if profile.free_text else {}
        except Exception:
            profile.interpreted = {}
    first_time = not profile.onboarded
    if profile.budget is not None:
        profile.onboarded = True
    db.commit()
    if first_time and profile.onboarded:
        request.session["welcome"] = True  # the home page will offer to build the first week right away
        return RedirectResponse("/", 303)
    return RedirectResponse("/survey?saved=1", 303)


@router.post("/pantry/add")
def pantry_add(
    request: Request,
    name: str = Form(""),
    quantity: str = Form(""),
    unit: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    name = name.strip().lower()
    if not name or len(name) > 100:
        return RedirectResponse("/survey?pantry_error=Enter+an+item+name", 303)
    qty = None
    if quantity.strip():
        try:
            qty = float(quantity)
        except ValueError:
            qty = -1
        if qty < 0 or qty != qty:
            return RedirectResponse("/survey?pantry_error=Quantity+must+be+a+positive+number", 303)
    existing = db.scalar(select(PantryItem).where(PantryItem.user_id == user.id, PantryItem.name == name))
    if existing:
        existing.quantity, existing.unit = qty, unit.strip()[:20]
    else:
        db.add(PantryItem(user_id=user.id, name=name, quantity=qty, unit=unit.strip()[:20]))
    db.commit()
    return RedirectResponse("/survey#pantry", 303)


@router.post("/pantry/{item_id}/delete")
def pantry_delete(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(PantryItem, item_id)
    if item and item.user_id == user.id:
        db.delete(item)
        db.commit()
    return RedirectResponse("/survey#pantry", 303)
