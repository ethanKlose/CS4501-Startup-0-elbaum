import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import CheckIn, Plan, User
from app.services import planner, inventory
from app.services.locking import lock_user
from app.services.weeks import plan_week_start

router = APIRouter()

OVERALL = {"great": "Great", "ok": "Fine", "poor": "Not good"}
COOK_TIME = {"too_much": "Too much cooking", "right": "About right", "could_do_more": "I could cook more"}
VARIETY = {"repetitive": "Too repetitive", "right": "About right"}


def checkin_due(plan: Optional[Plan], done: bool, now: Optional[dt.datetime] = None) -> bool:
    """Offer the check-in near the end of the week: weekend, or the plan is 6+ days old."""
    if not plan or plan.status != "ok" or done:
        return False
    now = now or dt.datetime.utcnow()
    if (plan.settings or {}).get("week_start"):
        return now.date() >= plan_week_start(plan) + dt.timedelta(days=5)
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
                  closed=inventory.closed(plan), overall=OVERALL, cook_time=COOK_TIME, variety=VARIETY, saved=request.query_params.get("saved"), leftovers=existing.leftovers if existing else [])


@router.post("/checkin")
def checkin_submit(
    overall: str = Form("ok"), cook_time: str = Form("right"), variety: str = Form("right"), notes: str = Form(""),
    bought_all: bool = Form(False), plan_id: int = Form(None),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    lock_user(db, user.id)
    plan = planner.latest_plan(db, user)
    if not plan or plan.status != "ok":
        return RedirectResponse("/", 303)
    if plan_id is not None and plan_id != plan.id:
        raise HTTPException(409, "This check-in is for an older plan. Reload before saving.")
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
    if first_time:
        if bought_all and not inventory.closed(plan):
            inventory.confirm_all_purchases(db, plan)
        left = inventory.settle(db, plan)
        row.leftovers = [l["name"] for l in left]
    db.commit()
    return RedirectResponse("/checkin?saved=1", 303)


@router.post('/checkin/undo')
def undo_checkin(request:Request,plan_id:int=Form(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    lock_user(db,user.id)
    plan=planner.latest_plan(db,user)
    if not plan or plan.id!=plan_id:raise HTTPException(409,'Only the latest plan can be reopened.')
    try:inventory.reopen(db,plan)
    except ValueError as e:
        db.rollback();raise HTTPException(409,str(e))
    row=db.scalar(select(CheckIn).where(CheckIn.plan_id==plan.id))
    if row:db.delete(row)
    db.commit()
    return RedirectResponse('/checkin',303)
