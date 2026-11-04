import json

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user_optional, render
from app.models import CheckIn, Plan
from app.routers.checkin import checkin_due
from app.routers.survey import get_profile
from app.services import planner, inventory
from app.services.analysis import sharing_stats
from app.services.calview import GRID_PX, HOUR_PX, HOUR_START, HOUR_END, build_columns, hour_labels, week_start_for, week_title
from app.services.schedule import build_sessions, day_label, sessions_by_day
from app.services.types import WEEKDAYS
from app.services.timing import timed_sessions
from app.services.weeks import plan_week_start

router = APIRouter()


def cook_note(m) -> str:
    """Short phrase for a meal card: when/how it gets cooked."""
    if m.cook_minutes == 0:
        return "no cooking"
    if m.cook_day == m.day:
        return "cook today"
    who = "Sunday" if m.cook_day < 0 else WEEKDAYS[m.cook_day]
    return f"from {who}'s batch" + (" ❄ thaw" if m.frozen else "")


def meals_json(meals, closed=False) -> str:
    """Everything the quick-view dialog needs, safe to embed in a <script type=application/json> tag."""
    out = {}
    for m in meals:
        out[m.id] = dict(
            id=m.id, name=m.name, slot=m.slot, day=WEEKDAYS[m.day], cook_minutes=m.cook_minutes, calories=m.calories,
            closed=closed, protein=m.protein, cost=round(m.cost, 2), status=m.status, pinned=m.pinned, rating=m.rating, note=cook_note(m),
            when=("Cook fresh today." if m.cook_day == m.day else
                  f"Cooked ahead on {day_label(m.cook_day)}{', frozen. Thaw the night before' if m.frozen else ' and kept in the fridge'}. Just reheat.") if m.cook_minutes else "No cooking needed.",
            steps=m.steps, ingredients=[f"{i['quantity']:g} {i['unit']} {i['name']}".replace("  ", " ") for i in m.ingredients])
    return json.dumps(out).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


@router.get("/")
def home(request: Request, user=Depends(current_user_optional), db: Session = Depends(get_db), plan_id: int = None):
    if user is None:
        return render(request, "landing.html", None)
    profile = get_profile(db, user)
    db.commit()
    if not profile.onboarded:
        return RedirectResponse("/survey", 303)
    latest = planner.latest_plan(db,user)
    plan = db.get(Plan,plan_id) if plan_id is not None else latest
    if plan_id is not None and (not plan or plan.user_id != user.id):
        raise HTTPException(404,"Plan not found")
    archived = bool(plan and latest and plan.id != latest.id)
    error = request.session.pop("flash_error", None)
    info = request.session.pop("flash_info", None)
    welcome = request.session.pop("welcome", False)
    ctx = dict(profile=profile, plan=plan, archived=archived, error=error, info=info, welcome=welcome, weekdays=WEEKDAYS)
    if not (plan and plan.status == "ok"):
        return render(request, "home.html", user, **ctx)

    meals = list(plan.meals)
    done = bool(db.scalar(select(CheckIn.id).where(CheckIn.plan_id == plan.id)))
    saved = [dict(m.as_dict(), cook_day=m.cook_day, frozen=m.frozen) for m in meals]
    sessions = build_sessions(saved)
    by_day = sessions_by_day(sessions)
    cook_plan = [dict(day=d, label=day_label(d), minutes=sum(x["minutes"] for x in by_day[d]), sessions=by_day[d]) for d in sorted(by_day)]
    start = plan_week_start(plan)
    cards = [dict(id=m.id, day=m.day, slot=m.slot, name=m.name, cost=m.cost, status=m.status, pinned=m.pinned, cook_day=m.cook_day,
                  frozen=m.frozen, cook_minutes=m.cook_minutes, note=cook_note(m)) for m in meals]
    st=plan.settings or {}
    timing=dict(cooking_windows=st.get('cooking_windows',{}),meal_times=st.get('meal_times',{}),earliest_day=st.get('earliest_day',-1),earliest_minute=st.get('earliest_minute',0))
    start_hour = min([HOUR_START] + [max(0, s["start"] // 60) for s in timed_sessions(sessions,**timing)])
    columns = build_columns(cards, sessions, plan.days, start, hour_start=start_hour,external_slots=st.get('external_slots',[]),**timing)
    active_days = {m.day for m in meals} or {0}
    n = len(active_days)
    stats = dict(calories=round(sum(m.calories for m in meals) / n), protein=round(sum(m.protein for m in meals) / n),
                 cooked=sum(m.status == "cooked" for m in meals), skipped=sum(m.status == "skipped" for m in meals), total=len(meals),
                 pct=min(100, round(plan.total_cost / plan.budget * 100)) if plan.budget else 0)
    return render(request, "home.html", user, columns=columns, hours=hour_labels(start_hour), hour_px=HOUR_PX, grid_px=(HOUR_END - start_hour) * HOUR_PX, week_title=week_title(start), stats=stats,
                  cook_plan=cook_plan, sharing=sharing_stats(m.as_dict() for m in meals), checkin_due=checkin_due(plan, done),
                  short=[w[:3] for w in WEEKDAYS], meals_json=meals_json(meals, inventory.closed(plan)), closed=inventory.closed(plan), prep_col=bool(columns and columns[0]["prep"]), **ctx)


router.add_api_route('/plans/{plan_id}',home,methods=['GET'])


@router.get('/plans')
def plan_history(request:Request,user=Depends(current_user_optional),db:Session=Depends(get_db)):
    if user is None:return RedirectResponse('/login',303)
    plans=list(db.scalars(select(Plan).where(Plan.user_id==user.id).order_by(Plan.id.desc())))
    return render(request,'history.html',user,plans=plans,week_start=plan_week_start)
