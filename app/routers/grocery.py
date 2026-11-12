from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, render
from app.models import GroceryCheck, User
from app.services import grocery, planner, inventory
from app.services.pricing import checkout
from app.services.preferences import get_preferences
from app.services.locking import lock_user

router = APIRouter()


@router.get("/grocery")
def grocery_list(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = planner.latest_plan(db, user)
    items = inventory.shopping_items(db, plan)
    checked = inventory.checked_keys(plan, items) if plan else set()
    package_rows=checkout(items,get_preferences(db,user.id).get('price_offers',{}),allow_unknown=True)
    remaining = sum(1 for i in items if i["key"] not in checked)
    return render(request, "grocery.html", user, plan=plan, checked=checked, remaining=remaining, items=items, groups=grocery.group_by_section(items),
                  package_rows=package_rows, checkout_total=round(sum(i["checkout_cost"] for i in package_rows),2), total=round(sum(i["cost"] for i in items), 2), closed=inventory.closed(plan))


@router.post("/grocery/toggle")
def toggle(key: str = Form(...), checked: bool = Form(...), plan_id: int = Form(None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
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


@router.post('/grocery/instacart')
def instacart_handoff(plan_id: int = Form(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    from fastapi import HTTPException
    from fastapi.responses import RedirectResponse
    from app.services.instacart import create_link,HandoffError
    lock_user(db,user.id)
    plan=planner.latest_plan(db,user)
    if not plan or plan.id!=plan_id:
        raise HTTPException(409,'The shopping list changed. Reload before sending it.')
    if inventory.closed(plan):
        raise HTTPException(409,'This plan is closed. Generate a new week before shopping.')
    items=inventory.shopping_items(db,plan)
    checked=inventory.checked_keys(plan,items)
    items=[i for i in items if i['key'] not in checked]
    if not items:
        return RedirectResponse('/grocery?handoff=empty',303)
    try:cache=create_link(items,(plan.settings or {}).get('instacart'))
    except HandoffError as e:
        return RedirectResponse('/grocery?handoff='+str(e),303)
    plan.settings=dict(plan.settings or {},instacart=cache)
    db.commit()
    return RedirectResponse(cache['url'],303)
