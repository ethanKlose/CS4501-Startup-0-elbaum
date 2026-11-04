from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user_optional, render
from app.routers.survey import get_profile

router = APIRouter()


@router.get("/")
def home(request: Request, user=Depends(current_user_optional), db: Session = Depends(get_db)):
    if user is None:
        return RedirectResponse("/login", 303)
    profile = get_profile(db, user)
    db.commit()
    if not profile.onboarded:
        return RedirectResponse("/survey", 303)
    return render(request, "home.html", user, profile=profile)
