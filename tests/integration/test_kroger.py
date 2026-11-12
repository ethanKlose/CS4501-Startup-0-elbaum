"""Actual routes, auth, CSRF, migrations, inventory and adapters; controlled Kroger HTTP."""
import copy
import json
import time
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.models import User
from app.services import kroger
from app.services.preferences import get_preferences,save_preferences
from tests.integration.helpers import onboard,generate,post,snapshot,shopping

pytestmark=pytest.mark.integration
UPC='0001111040101'


class KrogerProvider:
    def __init__(self):
        self.calls=[];self.cart_bodies=[];self.fail=None;self.refreshes=0;self.token_error=False
        self.stock='HIGH';self.price=2.49;self.no_stores=False;self.no_products=False

    def handle(self,transport,request):
        self.calls.append(request)
        url=str(request.url);method=request.method
        assert request.url.host=='api.kroger.com'
        if url==kroger.TOKEN_URL:
            assert request.headers['Authorization']==httpx.BasicAuth('test-kroger-client','test-kroger-secret')._auth_header
            form=parse_qs(request.content.decode())
            if self.token_error:return httpx.Response(400,json={'error':'invalid_grant','error_description':'private-test-token'})
            if form['grant_type']==['refresh_token']:
                self.refreshes+=1
                assert form['refresh_token']==['private-test-refresh']
            else:
                assert form['code']==['kroger-code'] and form['code_verifier'][0]
                assert form['redirect_uri']==['http://127.0.0.1:8000/integrations/kroger/callback']
            return httpx.Response(200,json=dict(access_token='private-test-token',refresh_token='private-test-refresh',
                expires_in=1800,token_type='bearer',scope='product.compact cart.basic:write'))
        assert request.headers['Authorization']=='Bearer private-test-token'
        if method=='PUT':
            assert request.url.path=='/v1/cart/add'
            self.cart_bodies.append(json.loads(request.content))
            if self.fail=='timeout':raise httpx.ReadTimeout('private-test-token',request=request)
            if self.fail=='redirect':return httpx.Response(302,headers={'Location':'https://evil.example.test'})
            if self.fail:return httpx.Response(self.fail,text='private-test-token test-kroger-secret')
            return httpx.Response(204)
        if self.fail and method=='GET':
            if self.fail=='timeout':raise httpx.ConnectTimeout('private-test-token',request=request)
            if self.fail=='malformed':return httpx.Response(200,text='private-test-token')
            return httpx.Response(self.fail if isinstance(self.fail,int) else 503,text='private-test-token')
        if request.url.path=='/v1/locations':
            assert request.url.params['filter.zipCode.near']=='22903'
            return httpx.Response(200,json={'data':[] if self.no_stores else [dict(locationId='02900372',name='Test Kroger',
                address={'addressLine1':'123 Test St','city':'Charlottesville','state':'VA','zipCode':'22903'})]})
        if request.url.path=='/v1/products':
            assert request.url.params['filter.locationId']=='02900372'
            assert request.url.params['filter.fulfillment'] in {'csp','dth'}
            assert request.url.params['filter.limit']=='5'
            return httpx.Response(200,json={'data':[] if self.no_products else [dict(upc=UPC,description='Kroger Rice',brand='Kroger',
                items=[dict(size='16 oz',price={'regular':self.price},inventory={'stockLevel':self.stock})])]})
        pytest.fail('Unexpected Kroger API request')


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('KROGER_CLIENT_ID','test-kroger-client')
    monkeypatch.setenv('KROGER_CLIENT_SECRET','test-kroger-secret')
    monkeypatch.setenv('KROGER_REDIRECT_URI','http://127.0.0.1:8000/integrations/kroger/callback')
    monkeypatch.setenv('KROGER_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    provider=KrogerProvider()
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',lambda transport,request:provider.handle(transport,request))
    return provider


def user_id(application):
    with application.sessions() as db:return db.scalar(select(User).where(User.email=='integration@example.test')).id


def prefs(application):
    with application.sessions() as db:return copy.deepcopy(get_preferences(db,user_id(application)))


def connect(web):
    response=post(web,'/integrations/kroger/connect')
    assert response.status_code==303
    query=parse_qs(httpx.URL(response.headers['location']).query.decode())
    assert set(query['scope'][0].split())==kroger.SCOPES
    assert query['code_challenge_method']==['S256']
    response=web.get('/integrations/kroger/callback',params={'state':query['state'][0],'code':'kroger-code'})
    assert response.status_code==303
    assert 'Kroger connected' in web.get('/integrations').text
    return query


def store(web):
    assert post(web,'/grocery/kroger/locations',{'zip_code':'22903'}).status_code==303
    assert 'Test Kroger' in web.get('/grocery/kroger').text
    assert post(web,'/grocery/kroger/store',{'location_id':'02900372','modality':'PICKUP'}).status_code==303


def draft(application,web,provider):
    onboard(web);generate(web);saved=snapshot(application);connect(web);store(web)
    assert post(web,'/grocery/kroger/start',{'plan_id':saved['id']}).status_code==303
    return saved,prefs(application)['kroger_draft']


def select_first(application,web,draft,index=0,packages=2):
    assert post(web,'/grocery/kroger/search',{'draft_id':draft['id'],'row_index':index,'term':'rice'}).status_code==303
    assert post(web,'/grocery/kroger/select',{'draft_id':draft['id'],'row_index':index,'upc':UPC,'packages':packages}).status_code==303
    fresh=prefs(application)['kroger_draft']
    assert fresh['rows'][index]['selection']['packages']==packages
    return fresh


def review(application,web,draft):
    response=web.get('/grocery/kroger/review',params={'draft_id':draft['id']})
    assert response.status_code==200,response.text
    assert 'Review before adding to Kroger' in response.text
    return prefs(application)['kroger_draft']['review_token']


def submit(web,draft,review_token):
    return post(web,'/grocery/kroger/cart',{'draft_id':draft['id'],'review_token':review_token,'confirmed':'true'})


def test_full_account_store_product_review_cart_flow_preserves_grocery_ledger(application,web,provider):
    saved,d=draft(application,web,provider)
    before=shopping(application,saved['id'])
    selected=select_first(application,web,d,packages=2)
    token=review(application,web,selected)
    assert len(provider.cart_bodies)==0  # Searching, selecting and reviewing never adds to cart.
    response=submit(web,d,token)
    assert response.status_code==303
    assert provider.cart_bodies==[{'items':[dict(upc=UPC,quantity=2,modality='PICKUP')]}]
    page=web.get('/grocery/kroger')
    assert 'Products were added' in page.text and '2 package(s)' in page.text
    assert snapshot(application)==saved
    assert shopping(application,saved['id'])==before  # In-cart is not purchased.
    data=prefs(application)
    assert data['kroger_draft']['state']=='sent'
    assert 'kroger_blocked_transfer' not in data
    assert 'private-test-token' not in json.dumps(data) and 'private-test-refresh' not in json.dumps(data)
    assert not any('/checkout' in str(call.url) for call in provider.calls)


@pytest.mark.parametrize('kind',['wrong','expired','replay','cancel','other_browser'])
def test_oauth_state_is_one_use_browser_bound_and_expiring(application,web,provider,kind):
    onboard(web)
    response=post(web,'/integrations/kroger/connect')
    query=parse_qs(httpx.URL(response.headers['location']).query.decode())
    state=query['state'][0]
    if kind=='expired':
        with application.sessions() as db:
            data=copy.deepcopy(get_preferences(db,user_id(application)))
            secret=kroger.unseal(data['kroger_pending']['secret'],user_id(application));secret['expires']=0
            data['kroger_pending']['secret']=kroger.seal(secret,user_id(application));save_preferences(db,user_id(application),data);db.commit()
    params={'state':'wrong' if kind=='wrong' else state,'code':'kroger-code'}
    if kind=='cancel':params['error']='access_denied'
    if kind=='other_browser':
        with application.client() as other:
            assert post(other,'/login',{'email':'integration@example.test','password':'IntegrationPass123!'}).status_code==303
            assert other.get('/integrations/kroger/callback',params=params).status_code==303
    else:
        assert web.get('/integrations/kroger/callback',params=params).status_code==303
    if kind=='replay':
        calls=len(provider.calls)
        assert web.get('/integrations/kroger/callback',params=params).status_code==303
        assert len(provider.calls)==calls
    else:
        assert 'kroger_connection' not in prefs(application)
        assert len(provider.calls)==0


def test_expired_token_refresh_persists_after_application_restart(application,web,provider):
    saved,d=draft(application,web,provider)
    with application.sessions() as db:
        data=copy.deepcopy(get_preferences(db,user_id(application)))
        value=kroger.unseal(data['kroger_connection'],user_id(application));value['expires']=0
        data['kroger_connection']=kroger.seal(value,user_id(application));save_preferences(db,user_id(application),data);db.commit()
    with application.client(cookies=web.cookies) as restarted:
        select_first(application,restarted,d)
    assert provider.refreshes==1
    assert kroger.unseal(prefs(application)['kroger_connection'],user_id(application))['expires']>time.time()


@pytest.mark.parametrize('change',['check_off','regenerate','store','expired','reconnect'])
def test_changed_list_store_connection_and_expired_review_cannot_transfer(application,web,provider,change):
    saved,d=draft(application,web,provider);d=select_first(application,web,d);token=review(application,web,d)
    if change=='check_off':
        first=shopping(application,saved['id'])[0]
        assert post(web,'/grocery/toggle',{'plan_id':saved['id'],'key':first['key'],'checked':'true'}).status_code==204
    elif change=='regenerate':assert post(web,'/plan/regenerate').status_code==303
    elif change=='store':assert post(web,'/grocery/kroger/store',{'location_id':'02900372','modality':'DELIVERY'}).status_code==303
    elif change=='reconnect':connect(web)
    else:
        with application.sessions() as db:
            data=copy.deepcopy(get_preferences(db,user_id(application)));data['kroger_draft']['expires']=0
            save_preferences(db,user_id(application),data);db.commit()
    assert submit(web,d,token).status_code==409
    assert provider.cart_bodies==[]


def test_double_submit_is_blocked_even_after_browser_restart(application,web,provider):
    saved,d=draft(application,web,provider);d=select_first(application,web,d);token=review(application,web,d)
    assert submit(web,d,token).status_code==303
    with application.client(cookies=web.cookies) as restarted:
        assert submit(restarted,d,token).status_code==409
    assert len(provider.cart_bodies)==1


@pytest.mark.parametrize('failure',['timeout','redirect',500])
def test_uncertain_write_is_never_retried_or_hidden_by_a_new_draft(application,web,provider,failure):
    saved,d=draft(application,web,provider);d=select_first(application,web,d);token=review(application,web,d)
    provider.fail=failure
    assert submit(web,d,token).status_code==303
    assert len(provider.cart_bodies)==1
    assert prefs(application)['kroger_blocked_transfer']['state']=='uncertain'
    assert submit(web,d,token).status_code==409
    assert post(web,'/grocery/kroger/start',{'plan_id':saved['id']}).status_code==303
    assert 'pending or its result is unknown' in web.get('/grocery/kroger').text
    assert len(provider.cart_bodies)==1
    assert post(web,'/grocery/kroger/acknowledge').status_code==422
    assert post(web,'/grocery/kroger/acknowledge',{'checked_cart':'true'}).status_code==303
    assert 'kroger_blocked_transfer' not in prefs(application)
    assert 'kroger_draft' not in prefs(application)
    assert snapshot(application)==saved


@pytest.mark.parametrize('status,code',[(400,'rejected'),(401,'reconnect'),(403,'permission'),(429,'quota')])
def test_explicit_rejection_records_failure_without_changing_inventory(application,web,provider,status,code):
    saved,d=draft(application,web,provider);d=select_first(application,web,d);token=review(application,web,d)
    provider.fail=status
    assert submit(web,d,token).status_code==303
    page=web.get('/grocery/kroger')
    assert 'private-test-token' not in page.text and 'test-kroger-secret' not in page.text
    assert prefs(application)['kroger_last_transfer']['state']=='rejected'
    assert 'kroger_blocked_transfer' not in prefs(application)
    assert snapshot(application)==saved and len(provider.cart_bodies)==1


def test_tampered_product_quantity_and_review_tokens_are_rejected_before_cart(application,web,provider):
    saved,d=draft(application,web,provider)
    assert post(web,'/grocery/kroger/search',{'draft_id':d['id'],'row_index':0,'term':'rice'}).status_code==303
    for data in [dict(upc='9999999999999',packages=1),dict(upc=UPC,packages=0),dict(upc=UPC,packages=100),dict(upc=UPC,packages='nan')]:
        assert post(web,'/grocery/kroger/select',{'draft_id':d['id'],'row_index':0,**data}).status_code==422
    d=select_first(application,web,d)
    assert submit(web,d,'forged').status_code==409
    token=review(application,web,d)
    # Changing a reviewed quantity invalidates the old confirmation token.
    assert post(web,'/grocery/kroger/select',{'draft_id':d['id'],'row_index':0,'upc':UPC,'packages':3}).status_code==303
    assert submit(web,d,token).status_code==409
    assert provider.cart_bodies==[]


def test_cart_transfer_requires_csrf_ownership_and_explicit_confirmation(application,web,provider):
    saved,d=draft(application,web,provider);d=select_first(application,web,d);token=review(application,web,d)
    assert web.post('/grocery/kroger/cart',data={'draft_id':d['id'],'review_token':token,'confirmed':'true'}).status_code==403
    assert post(web,'/grocery/kroger/cart',{'draft_id':d['id'],'review_token':token}).status_code==409
    with application.client() as other:
        onboard(other,'other-kroger@example.test')
        assert other.get('/grocery/kroger/review',params={'draft_id':d['id']}).status_code==303
        assert submit(other,d,token).status_code==303
    assert provider.cart_bodies==[]


def test_checked_and_pantry_ingredients_are_not_in_draft(application,web,provider):
    onboard(web);generate(web);saved=snapshot(application);connect(web);store(web)
    items=shopping(application,saved['id'])
    assert post(web,'/grocery/toggle',{'plan_id':saved['id'],'key':items[0]['key'],'checked':'true'}).status_code==204
    assert post(web,'/grocery/kroger/start',{'plan_id':saved['id']}).status_code==303
    keys={row['key'] for row in prefs(application)['kroger_draft']['rows']}
    assert items[0]['key'] not in keys
    assert keys=={row['key'] for row in items[1:]}


def test_unknown_stock_price_and_no_search_results_are_honest(application,web,provider):
    saved,d=draft(application,web,provider)
    provider.price=None;provider.stock='OUT_OF_STOCK'
    assert post(web,'/grocery/kroger/search',{'draft_id':d['id'],'row_index':0,'term':'rice'}).status_code==303
    page=web.get('/grocery/kroger')
    assert 'Price unavailable' in page.text and 'Reported out of stock' in page.text
    assert post(web,'/grocery/kroger/select',{'draft_id':d['id'],'row_index':0,'upc':UPC,'packages':1}).status_code==422
    provider.no_products=True
    post(web,'/grocery/kroger/search',{'draft_id':d['id'],'row_index':0,'term':'rice'})
    assert 'No matching products returned' in web.get('/grocery/kroger').text
    assert provider.cart_bodies==[]


def test_products_for_two_ingredients_merge_visibly_in_final_review(application,web,provider):
    saved,d=draft(application,web,provider)
    select_first(application,web,d,index=0,packages=2)
    d=select_first(application,web,d,index=1,packages=3)
    token=review(application,web,d)
    assert submit(web,d,token).status_code==303
    assert provider.cart_bodies==[{'items':[dict(upc=UPC,quantity=5,modality='PICKUP')]}]


def test_disconnect_removes_only_kroger_credentials_and_retains_unknown_write_marker(application,web,provider):
    saved,d=draft(application,web,provider)
    with application.sessions() as db:
        data=copy.deepcopy(get_preferences(db,user_id(application)))
        data['google_connection']='google-encrypted-value';data['kroger_blocked_transfer']={'draft_id':'old','at':time.time(),'state':'uncertain'}
        save_preferences(db,user_id(application),data);db.commit()
    assert post(web,'/integrations/kroger/disconnect').status_code==303
    data=prefs(application)
    assert 'kroger_connection' not in data and 'kroger_draft' not in data
    assert data['google_connection']=='google-encrypted-value'
    assert data['kroger_blocked_transfer']['state']=='uncertain'


def test_missing_credentials_and_bad_zip_do_not_contact_provider(application,web,provider,monkeypatch):
    onboard(web)
    assert post(web,'/integrations/kroger/connect').status_code==303
    connect_query=provider.calls[:]  # Connect only redirects; no provider call.
    assert connect_query==[]
    monkeypatch.delenv('KROGER_CLIENT_SECRET')
    assert post(web,'/integrations/kroger/connect').status_code==303
    assert 'local developer credentials' in web.get('/integrations').text
    assert provider.calls==[]


def test_concurrent_submit_sees_durable_sending_marker_before_provider_returns(application,web,provider,monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    saved,d=draft(application,web,provider);d=select_first(application,web,d);token=review(application,web,d)
    entered=threading.Event();release=threading.Event()
    def handler(transport,request):
        if request.method=='PUT':
            entered.set()
            assert release.wait(5),'Test did not release the controlled cart request'
        return provider.handle(transport,request)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',handler)
    with application.client(cookies=web.cookies) as second:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(submit,web,d,token)
            try:
                assert entered.wait(5)
                assert prefs(application)['kroger_blocked_transfer']['state']=='sending'
                assert submit(second,d,token).status_code==409
                assert post(second,'/grocery/kroger/acknowledge',{'checked_cart':'true'}).status_code==409
            finally:release.set()
            assert future.result(timeout=5).status_code==303
    assert len(provider.cart_bodies)==1


@pytest.mark.parametrize('failure',[401,403,429,'timeout','malformed'])
def test_search_errors_preserve_selected_products_and_groceries(application,web,provider,failure):
    saved,d=draft(application,web,provider);d=select_first(application,web,d)
    before=copy.deepcopy(prefs(application)['kroger_draft'])
    provider.fail=failure
    assert post(web,'/grocery/kroger/search',{'draft_id':d['id'],'row_index':0,'term':'rice'}).status_code==303
    assert prefs(application)['kroger_draft']==before
    assert snapshot(application)==saved and provider.cart_bodies==[]
    assert 'private-test-token' not in web.get('/grocery/kroger').text


def test_no_nearby_stores_is_visible_without_inventing_a_store(application,web,provider):
    onboard(web);connect(web);provider.no_stores=True
    assert post(web,'/grocery/kroger/locations',{'zip_code':'22903'}).status_code==303
    assert 'No Kroger-family stores were returned' in web.get('/grocery/kroger').text
    assert prefs(application)['kroger_locations']['items']==[]


def test_bad_zip_and_unoffered_store_do_not_create_store_selection(application,web,provider):
    onboard(web);connect(web)
    calls=len(provider.calls)
    assert post(web,'/grocery/kroger/locations',{'zip_code':'bad'}).status_code==303
    assert len(provider.calls)==calls
    assert post(web,'/grocery/kroger/store',{'location_id':'12345678','modality':'PICKUP'}).status_code==422
    assert 'kroger_store' not in prefs(application)
