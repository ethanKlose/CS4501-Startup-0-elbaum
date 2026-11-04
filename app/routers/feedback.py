import datetime as dt
import math
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from app.db import get_db
from app.deps import current_user,render
from app.services import planner
from app.services.preferences import get_preferences,save_preferences
from app.services.locking import lock_user

router=APIRouter()


@router.get('/feedback')
def feedback(request:Request,user=Depends(current_user),db=Depends(get_db)):
    return render(request,'feedback.html',user,entries=get_preferences(db,user.id).get('study_entries',[]))


@router.post('/feedback')
def record_feedback(actual_spend:float=Form(...),actual_minutes:int=Form(...),baseline_minutes:int=Form(...),ease:int=Form(...),notes:str=Form(''),consent:bool=Form(False),user=Depends(current_user),db=Depends(get_db)):
    if not math.isfinite(actual_spend) or not 0<=actual_spend<=10000 or not 0<=actual_minutes<=10080 or not 0<=baseline_minutes<=10080 or not 1<=ease<=5 or len(notes)>500:
        raise HTTPException(400,'Use nonnegative spending/time, an ease score from 1 to 5, and notes under 500 characters.')
    lock_user(db,user.id);prefs=get_preferences(db,user.id);plan=planner.latest_plan(db,user)
    record=dict(recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),plan_id=plan.id if plan else None,actual_spend=actual_spend,actual_minutes=actual_minutes,baseline_minutes=baseline_minutes,ease=ease,notes=notes.strip(),consent=consent,planned_meals=len(plan.meals) if plan else 0,cooked_meals=sum(m.status=='cooked' for m in plan.meals) if plan else 0,checkout_estimate=(plan.settings or {}).get('checkout_total') if plan else None)
    prefs['study_entries']=(prefs.get('study_entries',[])+[record])[-100:]
    save_preferences(db,user.id,prefs);db.commit()
    return RedirectResponse('/feedback?saved=1',303)
