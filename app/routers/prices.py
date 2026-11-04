import datetime as dt
import math
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from app.db import get_db
from app.deps import current_user,render
from app.services.preferences import get_preferences,save_preferences
from app.services.pricing import reference_offers
from app.services.locking import lock_user

router=APIRouter()


@router.get('/prices')
def prices(request:Request,user=Depends(current_user),db=Depends(get_db)):
    offers=reference_offers();offers.update(get_preferences(db,user.id).get('price_offers',{}))
    return render(request,'prices.html',user,offers=offers)


@router.post('/prices')
def save_price(key:str=Form(...),quantity:float=Form(...),price:float=Form(...),source:str=Form(...),observed_on:str=Form(...),user=Depends(current_user),db=Depends(get_db)):
    reference=reference_offers()
    if key not in reference or not math.isfinite(quantity) or quantity<=0 or not math.isfinite(price) or not 0<=price<=10000 or not source.strip() or len(source)>200:
        raise HTTPException(400,'Choose an ingredient and valid package size, price and source.')
    try:
        date=dt.date.fromisoformat(observed_on)
        if date>dt.date.today():raise ValueError()
    except ValueError:raise HTTPException(400,'Use a valid price-observation date, not a future date.')
    lock_user(db,user.id);prefs=get_preferences(db,user.id);offers=dict(prefs.get('price_offers',{}))
    offers[key]=dict(reference[key],package_quantity=quantity,package_price=round(price,2),source=source.strip(),observed_on=observed_on)
    prefs['price_offers']=offers;save_preferences(db,user.id,prefs);db.commit()
    return RedirectResponse('/prices?saved=1',303)
