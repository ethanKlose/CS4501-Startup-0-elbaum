"""Genuine provider calls: Google test event lifecycle and Instacart link creation.

Google needs an account already connected in the app. It creates one isolated
future test event and removes it in finally. Instacart creates a list link and
never a cart or order. Neither test calls an LLM or consumes OpenAI tokens.
"""
import datetime as dt
import os
import uuid
from types import SimpleNamespace

import pytest


def test_google_real_sync_update_and_cleanup(live_environment):
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import User
    from app.services import google_calendar as google
    from app.services.locking import lock_user
    from app.services.preferences import get_preferences, save_preferences
    email=os.environ.get('LIVE_GOOGLE_USER_EMAIL','').strip()
    if not email:
        pytest.fail('Set LIVE_GOOGLE_USER_EMAIL to the local account you connected through /integrations',pytrace=False)
    if not google.configured():
        pytest.fail('Complete Google setup in BETA_INTEGRATIONS.md first',pytrace=False)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==email))
        if not user:
            pytest.fail('No matching account exists in this local database',pytrace=False)
        lock_user(db,user.id)
        data=get_preferences(db,user.id)
        try:
            token=google.access_token(data,user.id)
        except google.CalendarError:
            pytest.fail('Connect this local account to Google Calendar in the app first',pytrace=False)
        save_preferences(db,user.id,data); db.commit()
    # Negative, random namespace cannot match any real positive local user ID.
    namespace=-int(uuid.uuid4().hex[:15],16)
    today=dt.date.today()
    week=today+dt.timedelta(days=7-today.weekday())
    class Meal(SimpleNamespace):
        def as_dict(self):
            return dict(day=self.day,slot=self.slot,name=self.name,cook_minutes=0,steps=self.steps)
    meal=Meal(id=1,day=0,slot='lunch',name='PlateJoy integration test — temporary',cook_minutes=0,cook_day=0,
              frozen=False,status='planned',steps=['This event will be removed by the test.'])
    plan=SimpleNamespace(id=1,settings={'week_start':week.isoformat()},meals=[meal])
    try:
        created=google.sync(plan,namespace,token)
        assert created==dict(created=1,updated=0,deleted=0,unchanged=0)
        # Second call uses the real read path and must not create a duplicate.
        repeated=google.sync(plan,namespace,token)
        assert repeated==dict(created=0,updated=0,deleted=0,unchanged=1)
        meal.steps=['Updated by the live integration test.']
        updated=google.sync(plan,namespace,token)
        assert updated==dict(created=0,updated=1,deleted=0,unchanged=0)
        live_environment.append(dict(service='google',created=1,repeated_unchanged=1,updated=1))
    finally:
        plan.meals=[]
        try:
            cleanup=google.sync(plan,namespace,token)
        except google.CalendarError:
            pytest.fail('Google cleanup could not finish. Remove the future event named PlateJoy integration test — temporary from your Calendar.',pytrace=False)
        live_environment.append(dict(service='google',cleanup_deleted=cleanup['deleted']))


def test_instacart_real_shopping_link_without_order(live_environment):
    from app.services.instacart import create_link, safe_url, HandoffError
    if not os.environ.get('INSTACART_API_KEY','').strip():
        pytest.fail('Set a separate Instacart developer key in .env first; an OpenAI key cannot authenticate Instacart',pytrace=False)
    try:
        result=create_link([dict(name='rice',quantity=1,unit='cup')])
    except HandoffError as exc:
        pytest.fail('Real Instacart request failed: '+str(exc),pytrace=False)
    assert safe_url(result['url'])
    assert result['fingerprint'] and result['created_at']>0
    live_environment.append(dict(service='instacart',shopping_links_created=1,orders_submitted=0))


def test_kroger_real_store_and_product_search_without_cart_write(live_environment):
    """Authenticates the saved real account, refreshes if needed and reads only."""
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import User
    from app.services import kroger
    from app.services.locking import lock_user
    from app.services.preferences import get_preferences,save_preferences
    import copy
    email=os.environ.get('LIVE_KROGER_USER_EMAIL','').strip()
    if not email:
        pytest.fail('Set LIVE_KROGER_USER_EMAIL to the local PlateJoy account connected to Kroger',pytrace=False)
    if not kroger.configured():
        pytest.fail('Complete the local developer settings in KROGER_SETUP.md first',pytrace=False)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==email))
        if not user:pytest.fail('No matching account exists in this local database',pytrace=False)
        lock_user(db,user.id)
        data=copy.deepcopy(get_preferences(db,user.id))
        try:token,_=kroger.access(data,user.id)
        except kroger.KrogerError:pytest.fail('Connect this local account to Kroger through Connected apps first',pytrace=False)
        save_preferences(db,user.id,data);db.commit()
    try:
        stores=kroger.locations(token,os.environ.get('LIVE_KROGER_ZIP','22903'))
        if not stores:pytest.fail('No Kroger-family store returned near this ZIP; choose another LIVE_KROGER_ZIP',pytrace=False)
        products=kroger.products(token,stores[0]['id'],'rice')
        if not products:pytest.fail('No products returned at this store for Pickup; verify store and API access in the app',pytrace=False)
    except kroger.KrogerError as exc:
        pytest.fail('Real Kroger read-only request failed: '+str(exc),pytrace=False)
    assert all(product['upc'].isdigit() and product['name'] for product in products)
    live_environment.append(dict(service='kroger',locations_returned=len(stores),products_returned=len(products),cart_writes=0,orders_submitted=0))
