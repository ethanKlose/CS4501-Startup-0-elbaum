from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import Meal, Plan, User
from app.services import planner, inventory
from app.services.locking import lock_user
from app.services.llm import get_llm

router = APIRouter()


@router.post("/plan/regenerate")
@router.post("/plan/generate")
def generate_plan(request: Request, start_mode: str = Form("keep"), user: User = Depends(current_user), db: Session = Depends(get_db), llm=Depends(get_llm)):
    try:
        if start_mode not in {"keep","today","next_week"}:
            raise HTTPException(422,"Invalid plan start")
        planner.generate(db, user, llm, start_mode=start_mode)
    except planner.PlanFailed as e:
        db.rollback()
        request.session["flash_error"] = {"message": e.message, "conflicts": e.conflicts}
    return RedirectResponse("/", 303)


@router.post("/plan/next-week")
def next_week(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), llm=Depends(get_llm)):
    try:
        planner.generate(db, user, llm, new_week=True)
    except planner.PlanFailed as e:
        db.rollback()
        request.session["flash_error"] = {"message": e.message, "conflicts": e.conflicts}
    return RedirectResponse("/", 303)


def owned_meal(db: Session, user: User, meal_id: int) -> Meal:
    lock_user(db, user.id)
    meal = db.get(Meal, meal_id)
    plan = db.get(Plan, meal.plan_id) if meal else None
    if not meal or plan.user_id != user.id:
        raise HTTPException(404, "Meal not found")
    return meal


@router.get("/meals/{meal_id}")
def meal_detail(meal_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.types import WEEKDAYS

    meal = owned_meal(db, user, meal_id)
    from app.services.schedule import day_label

    return render(request, "meal.html", user, meal=meal, weekday=WEEKDAYS[meal.day], closed=inventory.closed(db.get(Plan, meal.plan_id)), cook_label=day_label(meal.cook_day))


@router.post("/plan/days/{weekday}/skip")
def toggle_day(weekday: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
    plan = planner.latest_plan(db, user)
    if not plan or plan.status != "ok" or not 0 <= weekday <= 6:
        raise HTTPException(404, "No plan or day")
    currently = any(d["weekday"] == weekday and d.get("skipped") for d in plan.days)
    try:
        planner.set_day_skipped(db, plan, weekday, not currently)
    except planner.PlanFailed as e:
        db.rollback()
        request.session['flash_error'] = {'message': e.message, 'conflicts': []}
        return RedirectResponse('/', 303)
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
    if inventory.closed(db.get(Plan, meal.plan_id)):
        raise HTTPException(409, "This plan is closed. Its inventory has already been updated.")
    if status not in ("planned", "cooked", "skipped"):
        raise HTTPException(422, "status must be planned, cooked or skipped")
    meal.status = status
    db.commit()
    return RedirectResponse(next if next.startswith("/") and not next.startswith("//") else "/", 303)


@router.post("/meals/{meal_id}/rate")
def rate(meal_id: int, rating: int = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    meal = owned_meal(db, user, meal_id)
    if meal.status != "cooked":
        raise HTTPException(409, "Mark the meal as cooked before rating it")
    if not 1 <= rating <= 5:
        raise HTTPException(422, "rating must be 1-5")
    meal.rating = rating
    db.commit()
    return RedirectResponse(f"/meals/{meal.id}", 303)
