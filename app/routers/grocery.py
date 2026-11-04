from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import GroceryCheck, PantryItem, User
from app.services import grocery, planner

router = APIRouter()


@router.get("/grocery")
def grocery_list(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = planner.latest_plan(db, user)
    pantry = [dict(name=p.name, quantity=p.quantity, unit=p.unit)
              for p in db.scalars(select(PantryItem).where(PantryItem.user_id == user.id))]
    items = grocery.build_list(m.as_dict() for m in plan.meals) if plan and plan.status == "ok" else []
    items = grocery.apply_pantry(items, pantry)
    checked = {c.key for c in db.scalars(select(GroceryCheck).where(GroceryCheck.plan_id == plan.id))} if plan else set()
    remaining = sum(1 for i in items if i["key"] not in checked)
    return render(request, "grocery.html", user, plan=plan, checked=checked, remaining=remaining, items=items, groups=grocery.group_by_section(items),
                  total=round(sum(i["cost"] for i in items), 2))


@router.post("/grocery/toggle")
def toggle(key: str = Form(...), checked: bool = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = planner.latest_plan(db, user)
    if not plan or len(key) > 200:
        return Response(status_code=404)
    row = db.scalar(select(GroceryCheck).where(GroceryCheck.plan_id == plan.id, GroceryCheck.key == key))
    if checked and not row:
        db.add(GroceryCheck(plan_id=plan.id, key=key))
    elif not checked and row:
        db.delete(row)
    db.commit()
    return Response(status_code=204)
