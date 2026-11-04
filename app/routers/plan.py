from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import Meal, Plan, User
from app.services import planner
from app.services.llm import get_llm

router = APIRouter()


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
