from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user_optional, render
from app.routers.survey import get_profile
from app.models import CheckIn
from app.routers.checkin import checkin_due
from app.services import planner
from app.services.analysis import sharing_stats
from app.services.schedule import PRE_WEEK, build_sessions, day_label, sessions_by_day
from app.services.types import SLOTS, WEEKDAYS

router = APIRouter()


@router.get("/")
def home(request: Request, user=Depends(current_user_optional), db: Session = Depends(get_db)):
    if user is None:
        return render(request, "landing.html", None)
    profile = get_profile(db, user)
    db.commit()
    if not profile.onboarded:
        return RedirectResponse("/survey", 303)
    plan = planner.latest_plan(db, user)
    error = request.session.pop("flash_error", None)
    info = request.session.pop("flash_info", None)
    done = bool(plan and db.scalar(select(CheckIn.id).where(CheckIn.plan_id == plan.id)))
    skipped = {d["weekday"] for d in plan.days if d.get("skipped")} if plan else set()
    cook_plan = []
    if plan and plan.status == "ok":
        sessions = build_sessions(dict(m.as_dict(), cook_day=m.cook_day, frozen=m.frozen) for m in plan.meals)
        by_day = sessions_by_day(sessions)
        cook_plan = [dict(day=d, label=day_label(d), minutes=sum(x["minutes"] for x in by_day[d]), sessions=by_day[d])
                     for d in sorted(by_day)]
    sharing = sharing_stats(m.as_dict() for m in plan.meals) if plan and plan.status == "ok" else None
    return render(request, "home.html", user, profile=profile, plan=plan, error=error, weekdays=WEEKDAYS, slots=SLOTS, sharing=sharing, info=info, checkin_due=checkin_due(plan, done), skipped=skipped, cook_plan=cook_plan, day_label=day_label, short=[w[:3] for w in WEEKDAYS])
