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
    data.update(lifestyle_fields(form))
    save_preferences(db,user.id,data);db.commit()
    return RedirectResponse('/survey?saved=1#lifestyle',303)


def lifestyle_fields(form):
    return dict(
        equipment=sorted(set(form.getlist('equipment')) & set(EQUIPMENT)),
        cooking_skill=form.get('cooking_skill') if form.get('cooking_skill') in {'any','beginner'} else 'any',
        external_slots=[{'day':d,'slot':slot,'source':'Dining hall / eating elsewhere'}
                        for d in range(7) for slot in SLOTS if form.get(f'external_{d}_{slot}')],
    )


def parse_clock(raw):
    import re
    if not isinstance(raw,str) or not re.fullmatch(r"[0-9]{2}:[0-9]{2}",raw):
        raise ValueError("Use a 24-hour HH:MM time.")
    parts=raw.split(':')
    if len(parts)!=2 or not all(p.isdigit() for p in parts):raise ValueError('Use times such as 07:30.')
    hour,minute=map(int,parts)
    if not (0<=hour<=23 and 0<=minute<=59):raise ValueError('Time is outside the day.')
    return hour*60+minute


def schedule_fields(form):
    windows={}
    for day in range(7):
        raw=form.get(f'windows_{day}','').strip()
        if not raw:continue
        if len(raw)>127 or len(raw.split(','))>8:
            raise ValueError('Use at most eight cooking windows per day.')
        spans=[]
        for interval in raw.split(','):
            begin,end=map(str.strip,interval.split('-'))
            a,b=parse_clock(begin),parse_clock(end)
            if a>=b:raise ValueError('A cooking window must end after it begins.')
            spans.append([a,b])
        spans.sort()
        if any(a[1]>b[0] for a,b in zip(spans,spans[1:])):
            raise ValueError('Cooking windows must not overlap.')
        windows[str(day)]=spans
    meal_times={slot:parse_clock(form.get(f'time_{slot}',default))
                for slot,default in [('breakfast','08:00'),('lunch','12:30'),('dinner','18:30')]}
    if not meal_times['breakfast']<meal_times['lunch']<meal_times['dinner']:
        raise ValueError('Breakfast, lunch and dinner must be in that order.')
    return dict(cooking_windows=windows,meal_times=meal_times)


@router.post('/preferences/schedule')
async def schedule_preferences(request:Request,user=Depends(current_user),db=Depends(get_db)):
    from fastapi import HTTPException
    form=await request.form()
    try:
        fields=schedule_fields(form)
    except (ValueError,TypeError):
        raise HTTPException(400,'Use ordered HH:MM-HH:MM cooking windows separated by commas, and increasing meal times.')
    lock_user(db,user.id);data=get_preferences(db,user.id)
    data.update(fields)
    save_preferences(db,user.id,data);db.commit()
    return RedirectResponse('/survey?saved=1#schedule-windows',303)
