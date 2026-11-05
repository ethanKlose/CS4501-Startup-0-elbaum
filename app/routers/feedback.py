import datetime as dt
import math
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from app.db import get_db
from app.deps import current_user,render
from app.services import planner
from app.services.preferences import get_preferences,save_preferences
from app.services.locking import lock_user
from app.models import Plan

CORRECTNESS_FIELDS={'budget','diet','schedule','equipment','nutrition','coverage','extra_notes'}

router=APIRouter()


@router.get('/feedback')
def feedback(request:Request,user=Depends(current_user),db=Depends(get_db)):
    return render(request,'feedback.html',user,plan=planner.latest_plan(db,user),correctness_fields=sorted(CORRECTNESS_FIELDS),entries=get_preferences(db,user.id).get('study_entries',[]))


@router.post('/feedback')
def record_feedback(actual_spend:str=Form(''),actual_minutes:str=Form(''),baseline_minutes:str=Form(''),ease:str=Form(''),notes:str=Form(''),consent:bool=Form(False),plan_id:int=Form(None),plan_correct:str=Form('not_reviewed'),failed_constraints:list[str]=Form([]),user=Depends(current_user),db=Depends(get_db)):
    try:
        actual_spend=float(actual_spend) if actual_spend.strip() else None
        actual_minutes=int(actual_minutes) if actual_minutes.strip() else None
        baseline_minutes=int(baseline_minutes) if baseline_minutes.strip() else None
        ease=int(ease) if ease.strip() else None
    except (ValueError,TypeError):raise HTTPException(422,'Use numbers for spending and whole minutes or ease scores, or leave optional fields blank.')
    if (actual_spend is not None and (not math.isfinite(actual_spend) or not 0<=actual_spend<=10000)) or (actual_minutes is not None and not 0<=actual_minutes<=10080) or (baseline_minutes is not None and not 0<=baseline_minutes<=10080) or (ease is not None and not 1<=ease<=5) or len(notes)>500:
        raise HTTPException(400,'Use nonnegative spending/time, an ease score from 1 to 5, and notes under 500 characters.')
    if plan_correct not in {'yes','no','not_reviewed'} or set(failed_constraints)-CORRECTNESS_FIELDS or (plan_correct!='no' and failed_constraints):
        raise HTTPException(400,'Choose a valid correctness result and mark unmet constraints only when the plan did not meet them.')
    lock_user(db,user.id);prefs=get_preferences(db,user.id);plan=db.get(Plan,plan_id) if plan_id is not None else planner.latest_plan(db,user)
    if plan_id is not None and (not plan or plan.user_id!=user.id):raise HTTPException(404,'Plan not found')
    if not plan and plan_correct!='not_reviewed':raise HTTPException(400,'Create a plan before reviewing its correctness.')
    record=dict(recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(),plan_id=plan.id if plan else None,actual_spend=actual_spend,actual_minutes=actual_minutes,baseline_minutes=baseline_minutes,ease=ease,notes=notes.strip(),consent=consent,planned_meals=len(plan.meals) if plan else 0,cooked_meals=sum(m.status=='cooked' for m in plan.meals) if plan else 0,checkout_estimate=(plan.settings or {}).get('checkout_total') if plan else None)
    from app.services.verification import summary
    record.update(plan_correct=plan_correct,failed_constraints=sorted(set(failed_constraints)),correctness_source='student self-review',automatic_checks=summary(plan) if plan else None)
    prefs['study_entries']=(prefs.get('study_entries',[])+[record])[-100:]
    save_preferences(db,user.id,prefs);db.commit()
    return RedirectResponse('/feedback?saved=1',303)
