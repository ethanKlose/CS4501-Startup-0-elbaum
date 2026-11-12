"""Kroger connection and deliberate, server-reviewed grocery cart transfer."""
import copy
import hmac
import secrets
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.db import get_db
from app.deps import current_user, render
from app.services import inventory, kroger, planner
from app.services.kroger_display import summary as display_summary, ingredient_icon
from app.services.locking import lock_user
from app.services.preferences import get_preferences, save_preferences

router=APIRouter()
MESSAGES={
    'configuration':'Kroger needs local developer credentials. See KROGER_SETUP.md.',
    'connected':'Kroger connected. Open Grocery to choose a store and review products.',
    'cancelled':'Kroger connection cancelled. Your grocery list is unchanged.',
    'state':'This connection request expired or could not be verified. Connect Kroger again.',
    'reconnect':'Connect Kroger again to continue. Your grocery list is unchanged.',
    'provider':'Kroger could not be reached. Try this search or connection again later.',
    'response':'Kroger returned an unexpected response. Your grocery list is unchanged.',
    'permission':'Kroger did not grant the required API access. Check your app subscriptions and reconnect.',
    'quota':'Kroger is limiting requests. Wait before trying again.',
    'zip':'Enter a five-digit US ZIP code.',
    'search':'Use a search of 1–100 characters and at most eight words.',
    'size':'Start with 1–100 unchecked ingredients; split a larger list before using Kroger.',
    'selection':'Choose between 1 and 50 distinct products before reviewing the transfer.',
    'quantity':'Use 1–99 packages per product, including combined quantities for the same product.',
    'disconnected':'Kroger credentials were removed from this app. Existing cart items remain in Kroger.',
    'sent':'Products were added to your Kroger cart. Review your cart, prices and fulfillment details there before checkout.',
    'already_sent':'This transfer was already submitted. It was not sent again.',
    'uncertain':'Kroger did not confirm the result. Some products may already be in your cart. Check Kroger before allowing another transfer.',
    'in_progress':'A transfer is pending or its result is unknown. Check your Kroger cart before allowing another transfer.',
    'rejected':'Kroger rejected the request. Review the selected products and quantities before starting a fresh transfer.',
    'acknowledged':'You confirmed that you checked your Kroger cart. You can start a fresh, reviewed transfer.',
    'stale':'Your list, store or connection changed, or this review expired. Start a fresh review from Grocery.',
}


def prefs(db,user_id):
    return copy.deepcopy(get_preferences(db,user_id))


def finish(request,code,target='/grocery/kroger'):
    request.session['kroger_result']=code
    return RedirectResponse(target,303)


def persist(db,user_id,data):
    save_preferences(db,user_id,data);db.commit()


def token(db,user_id,data):
    try:
        access,connection=kroger.access(data,user_id)
    except kroger.KrogerError as exc:
        if str(exc)=='reconnect':
            data.pop('kroger_connection',None)
        raise
    # Callers retain their user lock until their own commit; refresh is persisted
    # alongside the operation, before any non-idempotent cart write.
    return access,connection


def groceries(db,user):
    plan=planner.latest_plan(db,user)
    if not plan or plan.status!='ok' or inventory.closed(plan):
        raise HTTPException(409,'Generate an active plan before shopping with Kroger.')
    items=inventory.shopping_items(db,plan)
    checked=inventory.checked_keys(plan,items)
    return plan,[i for i in items if i['key'] not in checked]


def draft_for(db,user,data,draft_id,connection_id=None):
    draft=data.get('kroger_draft')
    if not draft or draft['id']!=draft_id:
        raise HTTPException(409,MESSAGES['stale'])
    if data.get('kroger_blocked_transfer') or draft['state']=='sending':
        raise HTTPException(409,MESSAGES['in_progress'])
    if draft['state']=='sent':
        raise HTTPException(409,MESSAGES['already_sent'])
    if draft['state']!='editing' or draft['expires']<time.time():
        raise HTTPException(409,MESSAGES['stale'])
    plan,items=groceries(db,user)
    if (draft['plan_id']!=plan.id or draft['fingerprint']!=kroger.fingerprint(plan.id,items)
            or draft['store']!=data.get('kroger_store') or (connection_id is not None and draft['connection_id']!=connection_id)):
        raise HTTPException(409,MESSAGES['stale'])
    return draft


@router.post('/integrations/kroger/connect')
def connect(request:Request,user=Depends(current_user),db=Depends(get_db)):
    lock_user(db,user.id);data=prefs(db,user.id)
    try:url=kroger.begin(data,request.session,user.id)
    except kroger.KrogerError as exc:return finish(request,str(exc),'/integrations')
    persist(db,user.id,data)
    return RedirectResponse(url,303)


@router.get('/integrations/kroger/callback')
def callback(request:Request,state:str='',code:str='',error:str='',user=Depends(current_user),db=Depends(get_db)):
    lock_user(db,user.id);data=prefs(db,user.id)
    try:verifier=kroger.consume_state(data,request.session,state,user.id)
    except kroger.KrogerError as exc:
        persist(db,user.id,data)
        return finish(request,str(exc),'/integrations')
    persist(db,user.id,data)  # Consume callback once even if exchange times out.
    if error:return finish(request,'cancelled','/integrations')
    try:value=kroger.exchange(code,verifier)
    except kroger.KrogerError as exc:return finish(request,str(exc),'/integrations')
    lock_user(db,user.id);data=prefs(db,user.id)
    data['kroger_connection']=kroger.seal(value,user.id)
    data.pop('kroger_draft',None);data.pop('kroger_locations',None)
    # An unresolved external write survives reconnection/disconnection.
    persist(db,user.id,data)
    return finish(request,'connected','/integrations')


@router.post('/integrations/kroger/disconnect')
def disconnect(request:Request,user=Depends(current_user),db=Depends(get_db)):
    lock_user(db,user.id);data=prefs(db,user.id)
    for key in ('kroger_connection','kroger_pending','kroger_draft','kroger_locations','kroger_store'):
        data.pop(key,None)
    request.session.pop('kroger_oauth_state',None)
    persist(db,user.id,data)
    return finish(request,'disconnected','/integrations')


@router.get('/grocery/kroger')
def shop(request:Request,user=Depends(current_user),db=Depends(get_db)):
    data=prefs(db,user.id)
    code=request.session.pop('kroger_result','')
    plan=planner.latest_plan(db,user)
    choices=data.get('kroger_locations',{})
    rows=choices.get('items',[]) if choices.get('expires',0)>time.time() else []
    draft=data.get('kroger_draft')
    if draft and draft['expires']<time.time() and draft['state']=='editing':draft=None
    return render(request,'kroger_shop.html',user,plan=plan,configured=kroger.configured(),
        connected=bool(data.get('kroger_connection')),message=MESSAGES.get(code),locations=rows,
        location_search_done=choices.get('expires',0)>time.time(),store=data.get('kroger_store'),draft=draft,blocked=data.get('kroger_blocked_transfer'),last_transfer=data.get('kroger_last_transfer'),
        progress=display_summary(draft if draft and draft['state']=='editing' else None),ingredient_icon=ingredient_icon)


@router.post('/grocery/kroger/locations')
def find_locations(request:Request,zip_code:str=Form(...),user=Depends(current_user),db=Depends(get_db)):
    lock_user(db,user.id);data=prefs(db,user.id)
    try:
        access,_=token(db,user.id,data)
        rows=kroger.locations(access,zip_code.strip())
    except kroger.KrogerError as exc:
        persist(db,user.id,data)
        return finish(request,str(exc))
    data['kroger_locations']=dict(items=rows,expires=time.time()+600)
    persist(db,user.id,data)
    return RedirectResponse('/grocery/kroger#stores',303)


@router.post('/grocery/kroger/store')
def choose_store(request:Request,location_id:str=Form(...),modality:str=Form('PICKUP'),user=Depends(current_user),db=Depends(get_db)):
    lock_user(db,user.id);data=prefs(db,user.id)
    choices=data.get('kroger_locations',{})
    choice=next((row for row in choices.get('items',[]) if row['id']==location_id),None)
    if not choice or choices.get('expires',0)<time.time() or modality not in {'PICKUP','DELIVERY'}:
        raise HTTPException(422,'Choose a store returned by your recent ZIP search and Pickup or Delivery.')
    data['kroger_store']=dict(choice,modality=modality)
    data.pop('kroger_draft',None)
    persist(db,user.id,data)
    return RedirectResponse('/grocery/kroger',303)


@router.post('/grocery/kroger/start')
def start(request:Request,plan_id:int=Form(...),user=Depends(current_user),db=Depends(get_db)):
    lock_user(db,user.id);data=prefs(db,user.id)
    if data.get('kroger_blocked_transfer'):
        return finish(request,'in_progress')
    plan,items=groceries(db,user)
    if plan_id!=plan.id:raise HTTPException(409,MESSAGES['stale'])
    if not data.get('kroger_store'):raise HTTPException(409,'Choose a Kroger store first.')
    try:
        _,connection=token(db,user.id,data)
        data['kroger_draft']=kroger.new_draft(plan.id,items,data['kroger_store'],connection)
    except kroger.KrogerError as exc:
        persist(db,user.id,data)
        return finish(request,str(exc))
    persist(db,user.id,data)
    return RedirectResponse('/grocery/kroger#products',303)


@router.post('/grocery/kroger/search')
def search(request:Request,draft_id:str=Form(...),row_index:int=Form(...),term:str=Form(...),user=Depends(current_user),db=Depends(get_db)):
    lock_user(db,user.id);data=prefs(db,user.id)
    try:
        connection=kroger.unseal(data.get('kroger_connection',''),user.id)['connection_id']
        draft=draft_for(db,user,data,draft_id,connection)
        if not 0<=row_index<len(draft['rows']):raise HTTPException(404,'Ingredient not found.')
        access,_=token(db,user.id,data)
        results=kroger.products(access,draft['store']['id'],term,draft['store']['modality'])
    except kroger.KrogerError as exc:
        persist(db,user.id,data)
        return finish(request,str(exc))
    row=draft['rows'][row_index]
    row['candidates']=results;row['selection']=None;row['searched']=True
    draft.pop('review_token',None)
    persist(db,user.id,data)
    return RedirectResponse('/grocery/kroger#ingredient-'+str(row_index),303)


@router.post('/grocery/kroger/select')
def select_product(request:Request,draft_id:str=Form(...),row_index:int=Form(...),upc:str=Form(''),packages:int=Form(1,ge=1,le=99),user=Depends(current_user),db=Depends(get_db)):
    lock_user(db,user.id);data=prefs(db,user.id)
    # No network is needed to choose an already searched product.
    try:connection=kroger.unseal(data.get('kroger_connection',''),user.id)['connection_id']
    except kroger.KrogerError as exc:
        persist(db,user.id,data)
        return finish(request,str(exc))
    draft=draft_for(db,user,data,draft_id,connection)
    if not 0<=row_index<len(draft['rows']):raise HTTPException(404,'Ingredient not found.')
    row=draft['rows'][row_index]
    choice=next((candidate for candidate in row['candidates'] if candidate['upc']==upc and candidate['available']),None)
    if upc and not choice:raise HTTPException(422,'Choose an available product from this ingredient search.')
    row['selection']=dict(choice,packages=packages) if choice else None
    draft.pop('review_token',None)
    persist(db,user.id,data)
    return RedirectResponse('/grocery/kroger#ingredient-'+str(row_index),303)


@router.get('/grocery/kroger/review')
def review(request:Request,draft_id:str,user=Depends(current_user),db=Depends(get_db)):
    lock_user(db,user.id);data=prefs(db,user.id)
    try:connection=kroger.unseal(data.get('kroger_connection',''),user.id)['connection_id']
    except kroger.KrogerError as exc:
        persist(db,user.id,data)
        return finish(request,str(exc))
    draft=draft_for(db,user,data,draft_id,connection)
    try:items=kroger.cart_items(draft)
    except kroger.KrogerError as exc:
        persist(db,user.id,data)
        return finish(request,str(exc))
    draft.setdefault('review_token',secrets.token_urlsafe(24))
    persist(db,user.id,data)
    missing=sum(not row.get('selection') for row in draft['rows'])
    return render(request,'kroger_review.html',user,draft=draft,items=items,missing=missing,
        estimated_total=round(sum(i['quantity']*i['price'] for i in items if i['price'] is not None),2),
        unknown_price=any(i['price'] is None for i in items))


@router.post('/grocery/kroger/cart')
def send_cart(request:Request,draft_id:str=Form(...),review_token:str=Form(...),confirmed:bool=Form(False),user=Depends(current_user),db=Depends(get_db)):
    lock_user(db,user.id);data=prefs(db,user.id)
    try:
        connection=kroger.unseal(data.get('kroger_connection',''),user.id)['connection_id']
        draft=draft_for(db,user,data,draft_id,connection)
        items=kroger.cart_items(draft)
    except kroger.KrogerError as exc:
        persist(db,user.id,data)
        return finish(request,str(exc))
    if not confirmed or not draft.get('review_token') or not hmac.compare_digest(review_token,draft['review_token']):
        raise HTTPException(409,'Review the current products and explicitly confirm adding them to your cart.')
    try:access,_=token(db,user.id,data)
    except kroger.KrogerError as exc:
        persist(db,user.id,data)
        return finish(request,str(exc))
    receipt=dict(draft_id=draft_id,at=time.time(),products=len(items),packages=sum(i['quantity'] for i in items),state='sending')
    draft['state']='sending'
    data['kroger_blocked_transfer']=dict(receipt)
    data['kroger_last_transfer']=dict(receipt)
    persist(db,user.id,data)  # Durable before the external request; double-clicks cannot send again.
    code='sent'
    try:kroger.add_to_cart(access,items,draft['store']['modality'])
    except kroger.KrogerError as exc:code=str(exc)
    lock_user(db,user.id);db.expire_all();data=prefs(db,user.id)
    receipt['state']='sent' if code=='sent' else 'uncertain' if code=='uncertain' else 'rejected'
    if data.get('kroger_last_transfer',{}).get('draft_id')==draft_id:data['kroger_last_transfer']=receipt
    # The draft might have been removed by a concurrent local disconnect.
    if data.get('kroger_draft',{}).get('id')==draft_id:data['kroger_draft']['state']=receipt['state']
    if data.get('kroger_blocked_transfer',{}).get('draft_id')==draft_id:
        if receipt['state']=='uncertain':data['kroger_blocked_transfer']=dict(receipt)
        else:data.pop('kroger_blocked_transfer',None)
    if code=='reconnect':data.pop('kroger_connection',None)
    persist(db,user.id,data)
    return finish(request,code)


@router.post('/grocery/kroger/acknowledge')
def acknowledge(request:Request,checked_cart:bool=Form(False),user=Depends(current_user),db=Depends(get_db)):
    if not checked_cart:raise HTTPException(422,'Confirm you checked your Kroger cart before starting another transfer.')
    lock_user(db,user.id);data=prefs(db,user.id)
    blocked=data.get('kroger_blocked_transfer')
    if blocked and blocked['state']=='sending' and time.time()-blocked['at']<60:
        raise HTTPException(409,'The current request may still be running. Wait one minute and check Kroger first.')
    data.pop('kroger_blocked_transfer',None);data.pop('kroger_draft',None)
    persist(db,user.id,data)
    return finish(request,'acknowledged')
