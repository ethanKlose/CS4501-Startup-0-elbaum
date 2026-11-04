from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from app.db import get_db
from app.deps import current_user
from app.services.preferences import get_preferences, save_preferences
from app.services.lifestyle import EQUIPMENT
from app.services.types import SLOTS
from app.services.locking import lock_user

router=APIRouter()


@router.post('/preferences/lifestyle')
async def save(request:Request,user=Depends(current_user),db=Depends(get_db)):
    form=await request.form()
    lock_user(db,user.id)
    data=get_preferences(db,user.id)
    data['equipment']=sorted(set(form.getlist('equipment')) & set(EQUIPMENT))
    data['cooking_skill']=form.get('cooking_skill') if form.get('cooking_skill') in {'any','beginner'} else 'any'
    data['external_slots']=[{'day':d,'slot':slot,'source':'Dining hall / eating elsewhere'} for d in range(7) for slot in SLOTS if form.get(f'external_{d}_{slot}')]
    save_preferences(db,user.id,data);db.commit()
    return RedirectResponse('/survey?saved=1#lifestyle',303)
