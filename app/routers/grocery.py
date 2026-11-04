from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import GroceryCheck, User
from app.services import grocery, planner, inventory

router = APIRouter()


@router.get("/grocery")
def grocery_list(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = planner.latest_plan(db, user)
    items = inventory.shopping_items(db, plan)
    checked = inventory.checked_keys(plan, items) if plan else set()
    remaining = sum(1 for i in items if i["key"] not in checked)
    return render(request, "grocery.html", user, plan=plan, checked=checked, remaining=remaining, items=items, groups=grocery.group_by_section(items),
                  total=round(sum(i["cost"] for i in items), 2), closed=inventory.closed(plan))


@router.post("/grocery/toggle")
def toggle(key: str = Form(...), checked: bool = Form(...), plan_id: int = Form(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = planner.latest_plan(db, user)
    if not plan or len(key) > 200:
        return Response(status_code=404)
    if (plan_id is not None and plan_id != plan.id) or inventory.closed(plan):
        return Response(status_code=409)
    item = next((i for i in inventory.shopping_items(db, plan) if i['key'] == key), None)
    if item is None:
        item = inventory.purchases(plan).get(key)
    if item is None:
        return Response(status_code=404)
    inventory.record_purchase(db, plan, item, checked)
    row = db.scalar(select(GroceryCheck).where(GroceryCheck.plan_id == plan.id, GroceryCheck.key == key))
    if checked and not row:
        db.add(GroceryCheck(plan_id=plan.id, key=key))
    elif not checked and row:
        db.delete(row)
    db.commit()
    return Response(status_code=204)
