import math
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.services.llm import get_llm
from app.services.preferences import get_preferences,save_preferences
from app.services.locking import lock_user
from app.services.lifestyle import EQUIPMENT
from app.routers.lifestyle import lifestyle_fields, schedule_fields
from app.services.nutrition_goals import DEFAULT_PROTEIN, MIN_PROTEIN, MAX_PROTEIN, MIN_CALORIES, MAX_CALORIES, selected_goals
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
    "sesame_allergy": "Sesame allergy",
    "egg_free": "Egg-free",
    "halal": "Halal",
}
GOALS = {"none": "No specific goal", "high_protein": "High protein", "calorie_target": "Daily calorie target", "protein_calorie": "Protein and calorie targets"}
MIN_BUDGET = 30
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
    except (TypeError, ValueError, OverflowError):
        return None, "Enter your weekly grocery budget as a number."
    if v != v or v <= 0:
        return None, "Budget must be greater than zero."
    if v < MIN_BUDGET:
        return None, f"Enter a weekly budget of at least ${MIN_BUDGET}; generation will check whether a plan fits."
    if v > 10000:
        return None, "Budget looks too large — enter a weekly amount."
    return round(v, 2), None


def parse_minutes(raw: str):
    try:
        n = float(raw)
        if not math.isfinite(n) or not n.is_integer():
            return None
        v = int(n)
    except (TypeError, ValueError, OverflowError):
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


def apply_restrictions(form, profile, errors, **_):
    # Hidden marker field tells us the section was actually on the submitted form.
    if "restrictions_present" not in form:
        return
    submitted = form.getlist("restrictions")
    if any(r not in RESTRICTIONS for r in submitted):
        errors["restrictions"] = "Choose dietary restrictions from the list."
        return
    chosen = submitted
    profile.restrictions = sorted(set(chosen))


def integer_target(raw, lower, upper):
    try:
        number = float(raw)
        if math.isfinite(number) and number.is_integer() and lower <= number <= upper:
            return int(number)
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def apply_goal(form, profile, errors, **_):
    if 'goals_present' not in form and 'goal' not in form:
        return
    if 'goals_present' in form:
        chosen = set(form.getlist('goals'))
        if chosen - {'high_protein', 'calorie_target'}:
            errors['goal'] = 'Choose protein, calories, both, or neither.'
            return
        goal = ('protein_calorie' if len(chosen) == 2 else next(iter(chosen), 'none'))
    else:
        goal = form.get('goal', 'none')
        if goal not in GOALS:
            errors['goal'] = 'Pick a goal from the list.'
            return
        chosen = set(selected_goals(goal))
    protein = calories = None
    if 'high_protein' in chosen:
        # Legacy requests keep their 75g default; the Beta form always sends an exact amount.
        raw = form.get('protein_target', '' if 'goals_present' in form else str(DEFAULT_PROTEIN))
        protein = integer_target(raw, MIN_PROTEIN, MAX_PROTEIN)
        if protein is None:
            errors['protein_target'] = f'Enter a daily protein target between {MIN_PROTEIN} and {MAX_PROTEIN} grams, using a whole number.'
    if 'calorie_target' in chosen:
        calories = integer_target(form.get('calorie_target', ''), MIN_CALORIES, MAX_CALORIES)
        if calories is None:
            errors['calorie_target'] = f'Enter a daily calorie target between {MIN_CALORIES} and {MAX_CALORIES}, using a whole number.'
    if not errors:
        profile.goal, profile.protein_target, profile.calorie_target = goal, protein, calories


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
        n = float(form.get("prep_minutes", "120"))
        minutes = int(n) if math.isfinite(n) and n.is_integer() else 0
    except (TypeError, ValueError, OverflowError):
        minutes = 0
    if not 30 <= minutes <= MAX_MINUTES:
        errors["prep"] = f"A cooking session should be between 30 and {MAX_MINUTES} minutes."
        return
    profile.prep_style = style
    profile.prep_minutes = minutes
    profile.prep_days = sorted({int(d) for d in form.getlist("prep_days") if d in {str(i) for i in range(7)}})


APPLIERS = [apply_budget, apply_days, apply_restrictions, apply_goal, apply_free_text, apply_prep]


@router.get("/survey")
def survey_form(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = survey_context(db, user)
    values = field_values(ctx["profile"], ctx["days"])
    db.commit()
    return render(request, "survey.html", user, planning_error=request.session.pop("planning_error",None), errors={}, values=values, saved=request.session.pop("preferences_saved", False) or request.query_params.get("saved"), pantry_error=request.query_params.get("pantry_error"), **ctx)


def understood(profile: Profile, days) -> List[str]:
    """Plain-English readback of how we interpreted the answers, so surprises are visible before generating."""
    out = []
    if profile.restrictions:
        out.append("Diet: " + ", ".join(RESTRICTIONS[r] for r in profile.restrictions if r in RESTRICTIONS))
    interp = profile.interpreted or {}
    out.extend(interp.get('warnings', []))
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
    if "high_protein" in selected_goals(profile.goal):
        out.append(f"Goal: at least {profile.protein_target or DEFAULT_PROTEIN}g protein a day")
    if "calorie_target" in selected_goals(profile.goal) and profile.calorie_target:
        out.append(f"Goal: about {profile.calorie_target} calories a day")
    return out


def field_values(profile: Profile, days, form=None) -> dict:
    """What every input should show: the saved answers, or (after a rejected submit) what the user just typed."""
    if form is None:
        return dict(
            budget=profile.budget if profile.budget is not None else "", goal=profile.goal or "none",
            goals=selected_goals(profile.goal), protein_target=profile.protein_target or DEFAULT_PROTEIN,
            calorie_target=profile.calorie_target or "", free_text=profile.free_text or "",
            restrictions=list(profile.restrictions or []), prep_style=profile.prep_style or "auto",
            prep_days=[str(d) for d in (profile.prep_days or [])], prep_minutes=profile.prep_minutes or 120,
            days=[dict(weekday=d.weekday, busy=d.busy, minutes=d.minutes) for d in days])
    return dict(
        budget=form.get("budget", ""), goal=form.get("goal", profile.goal or "none"),
        goals=form.getlist("goals") if "goals_present" in form else selected_goals(form.get("goal", profile.goal)),
        protein_target=form.get("protein_target", profile.protein_target or DEFAULT_PROTEIN), calorie_target=form.get("calorie_target", ""),
        free_text=form.get("free_text", ""), restrictions=form.getlist("restrictions"),
        prep_style=form.get("prep_style", profile.prep_style or "auto"), prep_days=form.getlist("prep_days"),
        prep_minutes=form.get("prep_minutes", profile.prep_minutes or 120),
        days=[dict(weekday=d.weekday, busy=form.get(f"busy_{d.weekday}") is not None, minutes=form.get(f"minutes_{d.weekday}", d.minutes)) for d in days])


def survey_context(db, user, form=None):
    pantry = list(db.scalars(select(PantryItem).where(PantryItem.user_id == user.id).order_by(PantryItem.name)))
    profile, days = get_profile(db, user), get_days(db, user)
    lifestyle = get_preferences(db,user.id)
    import hashlib, json
    relevant={key:lifestyle[key] for key in ['equipment','cooking_skill','external_slots','cooking_windows','meal_times'] if key in lifestyle}
    preferences_version=hashlib.sha256(json.dumps([field_values(profile,days),relevant],sort_keys=True).encode()).hexdigest()
    if form is not None and 'lifestyle_present' in form:
        lifestyle.update(lifestyle_fields(form))
    window_values = {str(d): ', '.join(f'{a//60:02d}:{a%60:02d}-{b//60:02d}:{b%60:02d}'
                      for a,b in lifestyle.get('cooking_windows',{}).get(str(d),[])) for d in range(7)}
    time_values = {slot: f'{t//60:02d}:{t%60:02d}' for slot,t in
                   ((slot,lifestyle.get('meal_times',{}).get(slot,default))
                    for slot,default in [('breakfast',480),('lunch',750),('dinner',1110)])}
    if form is not None and 'schedule_present' in form:
        window_values = {str(d): form.get(f'windows_{d}', '') for d in range(7)}
        time_values = {slot: form.get(f'time_{slot}', '') for slot in time_values}
    return dict(preferences_version=preferences_version,lifestyle=lifestyle, window_values=window_values, time_values=time_values, equipment_options=EQUIPMENT, pantry=pantry, profile=profile, days=days, understood=understood(profile, days), weekdays=WEEKDAYS, restriction_options=RESTRICTIONS, goal_options=GOALS, prep_styles=PREP_STYLES)


@router.post("/survey/generate")
@router.post("/survey")
async def survey_submit(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), llm=Depends(get_llm)):
    form = await request.form()
    profile = get_profile(db, user)
    errors: Dict[str, str] = {}
    for fn in APPLIERS:
        fn(form=form, profile=profile, errors=errors, db=db, user=user)
    extra = {}
    if 'lifestyle_present' in form:
        extra.update(lifestyle_fields(form))
    if 'schedule_present' in form:
        try:
            extra.update(schedule_fields(form))
        except (ValueError, TypeError):
            errors['schedule'] = 'Check meal times and cooking windows: use ordered HH:MM-HH:MM windows without overlaps, and breakfast before lunch before dinner.'
    if errors:
        db.rollback()
        ctx = survey_context(db, user, form)
        db.rollback()
        return render(request, "survey.html", user, 400, errors=errors, values=field_values(ctx["profile"], ctx["days"], form), **ctx)
    if "free_text" in form:  # remember how the note was understood, to show it back to the user
        try:
            profile.interpreted = llm.interpret_preferences(profile.free_text) if profile.free_text else {}
        except Exception:
            profile.interpreted = {}
    if extra:
        preferences = get_preferences(db, user.id)
        preferences.update(extra)
        save_preferences(db, user.id, preferences)
    first_time = not profile.onboarded
    if profile.budget is not None:
        profile.onboarded = True
    db.commit()
    if request.url.path == "/survey/generate":
        # Save every section before building. A failed generation rolls back
        # inventory/plan changes while retaining the user's saved preferences.
        from app.services import planner
        request.session.pop("welcome", None)
        request.session["preferences_saved"] = True
        try:
            await run_in_threadpool(planner.generate, db, user, llm, start_mode="keep")
        except planner.PlanFailed as exc:
            db.rollback()
            if getattr(exc,"redirect_to_preferences",False):
                request.session["planning_error"]={"message":exc.message,"details":exc.errors}
                return RedirectResponse("/survey",303)
            request.session["flash_error"] = {"message": "Preferences saved, but the new plan could not be generated. Your previous plan is still available. " + exc.message, "conflicts": exc.conflicts}
        return RedirectResponse("/", 303)
    if first_time and profile.onboarded:
        request.session["welcome"] = True  # the home page will offer to build the first week right away
        return RedirectResponse("/", 303)
    return RedirectResponse("/survey?saved=1", 303)


def pantry_response(request, db, user, error=None, message='Pantry updated.', status=200):
    if 'application/json' in request.headers.get('accept',''):
        if error:
            return JSONResponse({'ok':False,'error':error},status_code=status,headers={'Cache-Control':'no-store'})
        rows=list(db.scalars(select(PantryItem).where(PantryItem.user_id==user.id).order_by(PantryItem.name)))
        body=render(request,'_pantry_body.html',user,pantry=rows,pantry_error=None).body.decode()
        return JSONResponse({'ok':True,'html':body,'message':message},headers={'Cache-Control':'no-store'})
    if error:
        from urllib.parse import quote
        return RedirectResponse('/survey?pantry_error='+quote(error),303)
    return RedirectResponse('/survey#pantry',303)


@router.get('/pantry')
def pantry_snapshot(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return pantry_response(request,db,user,message='Pantry refreshed.')


@router.post('/pantry/add')
def pantry_add(request:Request,name:str=Form(''),quantity:str=Form(''),unit:str=Form(''),
               user:User=Depends(current_user),db:Session=Depends(get_db)):
    name=name.strip().lower()
    if not name or len(name)>100:
        return pantry_response(request,db,user,'Enter an item name of 1–100 characters.',status=400)
    qty=None
    if quantity.strip():
        try:qty=float(quantity)
        except ValueError:qty=-1
        if qty<0 or not math.isfinite(qty) or qty>1_000_000:
            return pantry_response(request,db,user,'Quantity must be between 0 and 1000000.',status=400)
    unit=unit.lower().strip()
    if len(unit)>20:
        return pantry_response(request,db,user,'Unit must be 20 characters or fewer.',status=400)
    lock_user(db,user.id)
    existing=db.scalar(select(PantryItem).where(PantryItem.user_id==user.id,PantryItem.name==name,PantryItem.unit==unit))
    if existing:existing.quantity,existing.unit=qty,unit
    else:
        if len(list(db.scalars(select(PantryItem.id).where(PantryItem.user_id==user.id))))>=200:
            db.rollback()
            return pantry_response(request,db,user,'Pantry limit is 200 items.',status=400)
        db.add(PantryItem(user_id=user.id,name=name,quantity=qty,unit=unit))
    db.commit()
    return pantry_response(request,db,user,message='Added '+name+' to your pantry.')


@router.post('/pantry/{item_id}/delete')
def pantry_delete(item_id:int,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    lock_user(db,user.id)
    item=db.get(PantryItem,item_id)
    if item and item.user_id==user.id:
        db.delete(item);db.commit()
        return pantry_response(request,db,user,message='Removed the pantry item.')
    db.rollback()
    if 'application/json' in request.headers.get('accept',''):
        return pantry_response(request,db,user,'Pantry item not found.',status=404)
    return RedirectResponse('/survey#pantry',303)
