from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import Meal, Plan, User
from app.services import planner
from app.services.llm import get_llm

router = APIRouter()


@router.post("/plan/regenerate")
@router.post("/plan/generate")
def generate_plan(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), llm=Depends(get_llm)):
    try:
        planner.generate(db, user, llm)
    except planner.PlanFailed as e:
        request.session["flash_error"] = {"message": e.message, "conflicts": e.conflicts}
    return RedirectResponse("/", 303)


def owned_meal(db: Session, user: User, meal_id: int) -> Meal:
    meal = db.get(Meal, meal_id)
    plan = db.get(Plan, meal.plan_id) if meal else None
    if not meal or plan.user_id != user.id:
        raise HTTPException(404, "Meal not found")
    return meal


@router.get("/meals/{meal_id}")
def meal_detail(meal_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.types import WEEKDAYS

    meal = owned_meal(db, user, meal_id)
    return render(request, "meal.html", user, meal=meal, weekday=WEEKDAYS[meal.day])


@router.post("/plan/days/{weekday}/skip")
def toggle_day(weekday: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = planner.latest_plan(db, user)
    if not plan or plan.status != "ok" or not 0 <= weekday <= 6:
        raise HTTPException(404, "No plan or day")
    currently = any(d["weekday"] == weekday and d.get("skipped") for d in plan.days)
    planner.set_day_skipped(db, plan, weekday, not currently)
    if currently:
        request.session["flash_info"] = "Day restored. Regenerate to fill it (your pinned meals are kept)."
    return RedirectResponse("/", 303)


@router.post("/meals/{meal_id}/pin")
def toggle_pin(meal_id: int, request: Request, next: str = Form("/"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    meal = owned_meal(db, user, meal_id)
    meal.pinned = not meal.pinned
    db.commit()
    return RedirectResponse(next if next.startswith("/") and not next.startswith("//") else "/", 303)


@router.post("/meals/{meal_id}/swap")
def swap(meal_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), llm=Depends(get_llm)):
    meal = owned_meal(db, user, meal_id)
    try:
        planner.swap_meal(db, user, llm, meal)
    except planner.PlanFailed as e:
        db.rollback()
        request.session["flash_error"] = {"message": "Couldn't swap that meal: " + e.message, "conflicts": e.conflicts}
    return RedirectResponse("/", 303)


@router.post("/meals/{meal_id}/status")
def set_status(meal_id: int, status: str = Form(...), next: str = Form("/"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    meal = owned_meal(db, user, meal_id)
    if status not in ("planned", "cooked", "skipped"):
        raise HTTPException(422, "status must be planned, cooked or skipped")
    meal.status = status
    db.commit()
    return RedirectResponse(next if next.startswith("/") and not next.startswith("//") else "/", 303)
