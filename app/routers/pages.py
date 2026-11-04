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
from app.services.prep import prep_blocks
from app.services.types import SLOTS, WEEKDAYS

router = APIRouter()


@router.get("/")
def home(request: Request, user=Depends(current_user_optional), db: Session = Depends(get_db)):
    if user is None:
        return RedirectResponse("/login", 303)
    profile = get_profile(db, user)
    db.commit()
    if not profile.onboarded:
        return RedirectResponse("/survey", 303)
    plan = planner.latest_plan(db, user)
    error = request.session.pop("flash_error", None)
    info = request.session.pop("flash_info", None)
    done = bool(plan and db.scalar(select(CheckIn.id).where(CheckIn.plan_id == plan.id)))
    skipped = {d["weekday"] for d in plan.days if d.get("skipped")} if plan else set()
    prep = prep_blocks([m.as_dict() for m in plan.meals], plan.days) if plan and plan.status == "ok" else []
    sharing = sharing_stats(m.as_dict() for m in plan.meals) if plan and plan.status == "ok" else None
    return render(request, "home.html", user, profile=profile, plan=plan, error=error, weekdays=WEEKDAYS, slots=SLOTS, sharing=sharing, info=info, checkin_due=checkin_due(plan, done), skipped=skipped, prep={b["day"]: b for b in prep})
