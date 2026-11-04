from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import PantryItem, User
from app.services import grocery, planner

router = APIRouter()


@router.get("/grocery")
def grocery_list(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = planner.latest_plan(db, user)
    pantry = [dict(name=p.name, quantity=p.quantity, unit=p.unit)
              for p in db.scalars(select(PantryItem).where(PantryItem.user_id == user.id))]
    items = grocery.build_list(m.as_dict() for m in plan.meals) if plan and plan.status == "ok" else []
    items = grocery.apply_pantry(items, pantry)
    return render(request, "grocery.html", user, plan=plan, items=items,
                  total=round(sum(i["cost"] for i in items), 2))
