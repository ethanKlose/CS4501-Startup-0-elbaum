from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user_optional, render
from app.routers.survey import get_profile
from app.services import planner
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
    return render(request, "home.html", user, profile=profile, plan=plan, error=error, weekdays=WEEKDAYS, slots=SLOTS)
