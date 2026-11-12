"""Stories #27-#32: provider contract, failures, status/rating integrity and check-in validation.

MockTransport verifies the integration contract without contacting Instacart.
"""
import copy
import httpx
import pytest
from app.services import instacart
from app.models import CheckIn,Meal,Plan
from tests.helpers import signup

ITEMS=[dict(name='rice',unit='cup',quantity=2)]

@pytest.fixture
def planned(client):
    signup(client);client.post('/survey',data={'budget':'150'});client.post('/plan/generate')
    return client

@pytest.mark.parametrize('url',['http://instacart.com/list','https://instacart.com.evil.test/a','https://evil.test/a','https://user@instacart.com/a','https://instacart.com:444/a'])
def test_untrusted_return_urls_rejected(url):assert not instacart.safe_url(url)


def test_contract_and_cache_avoid_duplicate_requests(monkeypatch):
    monkeypatch.setenv('INSTACART_API_KEY','unit-test-key')
    calls=[];original=httpx.Client
    def handler(request):
        import json
        calls.append(request)
        body=json.loads(request.content)
        assert body['line_items'][0]['line_item_measurements']==[{'quantity':len(calls)+1,'unit':'cup'}]
        assert 'quantity' not in body['line_items'][0]
        assert request.headers['Authorization']=='Bearer unit-test-key'
        return httpx.Response(200,json={'products_link_url':'https://www.instacart.com/store/list/test'})
    monkeypatch.setattr(instacart.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    a=instacart.create_link(ITEMS)
    assert instacart.create_link(ITEMS,a)==a and len(calls)==1
    instacart.create_link([dict(ITEMS[0],quantity=3)],a)
    assert len(calls)==2

@pytest.mark.parametrize('failure',['timeout','status','json','url'])
def test_provider_failures_never_return_provider_text_or_key(monkeypatch,failure):
    monkeypatch.setenv('INSTACART_API_KEY','secret-test-key');original=httpx.Client
    def handler(request):
        if failure=='timeout':raise httpx.ReadTimeout('secret-test-key')
        if failure=='status':return httpx.Response(401,text='secret-test-key')
        if failure=='json':return httpx.Response(200,text='not json')
        return httpx.Response(200,json={'products_link_url':'https://evil.test/list'})
    monkeypatch.setattr(instacart.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(instacart.HandoffError) as e:instacart.create_link(ITEMS)
    assert str(e.value) in {'provider','response'}


def test_unavailable_handoff_keeps_the_plan_and_list(planned,monkeypatch):
    monkeypatch.delenv('INSTACART_API_KEY',raising=False)
    with planned.app.state.session_factory() as db:pid=db.query(Plan).first().id
    r=planned.post('/grocery/instacart',data={'plan_id':pid})
    assert r.status_code==200 and 'not configured yet' in r.text
    assert 'Send to Instacart' in r.text
    assert planned.post('/grocery/instacart',data={'plan_id':pid+100}).status_code==409


def test_handoff_only_sends_unchecked_items(planned,monkeypatch):
    from app.services import inventory
    with planned.app.state.session_factory() as db:
        p=db.query(Plan).first();pid=p.id
        first=inventory.shopping_items(db,p)[0]
        inventory.record_purchase(db,p,first);db.commit()
    sent=[]
    def fake(items,cache):
        sent.extend(items);return dict(url='https://www.instacart.com/store/list/test')
    monkeypatch.setattr(instacart,'create_link',fake)
    r=planned.post('/grocery/instacart',data={'plan_id':pid},follow_redirects=False)
    assert r.status_code==303 and r.headers['location'].startswith('https://www.instacart.com/')
    assert all(i['key']!=first['key'] for i in sent)


def test_reset_status_removes_a_rating_from_future_preferences(planned):
    with planned.app.state.session_factory() as db:mid=db.query(Meal).first().id
    planned.post(f'/meals/{mid}/status',data={'status':'cooked'})
    planned.post(f'/meals/{mid}/rate',data={'rating':'5'})
    planned.post(f'/meals/{mid}/status',data={'status':'skipped'})
    with planned.app.state.session_factory() as db:assert db.get(Meal,mid).rating is None

@pytest.mark.parametrize('data',[{'notes':'x'*501},{'overall':'unknown'},{'cook_time':'unknown'},{'variety':'unknown'}])
def test_invalid_checkin_does_not_close_or_settle_plan(planned,data):
    assert planned.post('/checkin',data=data).status_code==422
    with planned.app.state.session_factory() as db:
        assert db.query(CheckIn).count()==0
        assert not (db.query(Plan).first().settings or {}).get('inventory',{}).get('settled')
