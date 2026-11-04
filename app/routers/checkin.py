import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import CheckIn, GroceryCheck, PantryItem, Plan, User
from app.services import grocery, planner

router = APIRouter()

OVERALL = {"great": "Great", "ok": "Fine", "poor": "Not good"}
COOK_TIME = {"too_much": "Too much cooking", "right": "About right", "could_do_more": "I could cook more"}
VARIETY = {"repetitive": "Too repetitive", "right": "About right"}


def checkin_due(plan: Optional[Plan], done: bool, now: Optional[dt.datetime] = None) -> bool:
    """Offer the check-in near the end of the week: weekend, or the plan is 6+ days old."""
    if not plan or plan.status != "ok" or done:
        return False
    now = now or dt.datetime.utcnow()
    return now.weekday() >= 5 or (now - plan.created_at).days >= 6


def week_summary(meals) -> dict:
    cooked = [m for m in meals if m.status == "cooked"]
    rated = [m.rating for m in meals if m.rating]
    return dict(total=len(meals), cooked=len(cooked), skipped=sum(m.status == "skipped" for m in meals),
                avg_rating=round(sum(rated) / len(rated), 1) if rated else None)


@router.get("/checkin")
def checkin_form(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = planner.latest_plan(db, user)
    existing = db.scalar(select(CheckIn).where(CheckIn.plan_id == plan.id)) if plan else None
    return render(request, "checkin.html", user, plan=plan, existing=existing, summary=week_summary(plan.meals) if plan and plan.status == "ok" else None,
                  overall=OVERALL, cook_time=COOK_TIME, variety=VARIETY, saved=request.query_params.get("saved"), leftovers=existing.leftovers if existing else [])


@router.post("/checkin")
def checkin_submit(
    overall: str = Form("ok"), cook_time: str = Form("right"), variety: str = Form("right"), notes: str = Form(""),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    plan = planner.latest_plan(db, user)
    if not plan or plan.status != "ok":
        return RedirectResponse("/", 303)
    row = db.scalar(select(CheckIn).where(CheckIn.plan_id == plan.id))
    first_time = row is None
    if first_time:
        row = CheckIn(user_id=user.id, plan_id=plan.id)
        db.add(row)
    row.overall = overall if overall in OVERALL else "ok"
    row.cook_time = cook_time if cook_time in COOK_TIME else "right"
    row.variety = variety if variety in VARIETY else "right"
    row.notes = notes.strip()[:500]
    row.created_at = dt.datetime.utcnow()
    if first_time:  # leftovers move to the pantry exactly once per week
        checked = [c.key for c in db.scalars(select(GroceryCheck).where(GroceryCheck.plan_id == plan.id))]
        left = grocery.leftovers_from(plan.meals, checked)
        row.leftovers = [l["name"] for l in left]
        add_to_pantry(db, user, left)
    db.commit()
    return RedirectResponse("/checkin?saved=1", 303)


def add_to_pantry(db: Session, user: User, leftovers) -> None:
    for l in leftovers:
        item = db.scalar(select(PantryItem).where(PantryItem.user_id == user.id, PantryItem.name == l["name"]))
        if item is None:
            db.add(PantryItem(user_id=user.id, name=l["name"], quantity=l["quantity"], unit=l["unit"]))
        elif item.quantity is not None and (item.unit or "") == l["unit"]:
            item.quantity = round(item.quantity + l["quantity"], 2)
        # quantity-less ("I have plenty") or different-unit entries are left as the user wrote them
