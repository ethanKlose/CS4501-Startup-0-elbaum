from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import Profile, User

router = APIRouter()


def get_profile(db: Session, user: User) -> Profile:
    p = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if p is None:
        p = Profile(user_id=user.id)
        db.add(p)
        db.flush()
    return p


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


@router.get("/survey")
def survey_form(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "survey.html", user, profile=get_profile(db, user), errors={}, saved=request.query_params.get("saved"))


@router.post("/survey")
def survey_submit(
    request: Request,
    budget: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    profile = get_profile(db, user)
    errors = {}
    value, err = parse_budget(budget)
    if err:
        errors["budget"] = err
    else:
        profile.budget = value
    if errors:
        db.rollback()
        return render(request, "survey.html", user, 400, profile=profile, errors=errors, form={"budget": budget})
    db.commit()
    return RedirectResponse("/survey?saved=1", 303)
