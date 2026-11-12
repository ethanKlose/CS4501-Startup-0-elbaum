"""Kroger credential, identifier, payload and quantity boundaries; no real I/O."""
import json
import time

import httpx
import pytest
from cryptography.fernet import Fernet

from app.services import kroger


@pytest.fixture
def config(monkeypatch):
    for key in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setenv('SECRET_KEY','a-private-test-session-secret-long-enough')
    monkeypatch.setenv('KROGER_CLIENT_ID','test-client')
    monkeypatch.setenv('KROGER_CLIENT_SECRET','test-secret')
    monkeypatch.setenv('KROGER_REDIRECT_URI','http://127.0.0.1:8000/integrations/kroger/callback')
    monkeypatch.setenv('KROGER_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())


@pytest.mark.parametrize('uri',['http://evil.test/integrations/kroger/callback','https://example.test/wrong',
    'https:///integrations/kroger/callback','https://u:p@example.test/integrations/kroger/callback',
    'https://example.test/integrations/kroger/callback?next=evil','https://example.test:bad/integrations/kroger/callback'])
def test_invalid_redirect_configuration_disables_kroger(config,monkeypatch,uri):
    monkeypatch.setenv('KROGER_REDIRECT_URI',uri)
    assert not kroger.configured()


def test_kroger_can_reuse_google_encryption_key_without_google_client_credentials(config,monkeypatch):
    monkeypatch.delenv('KROGER_TOKEN_ENCRYPTION_KEY')
    monkeypatch.setenv('GOOGLE_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    monkeypatch.delenv('GOOGLE_CLIENT_ID',raising=False);monkeypatch.delenv('GOOGLE_CLIENT_SECRET',raising=False)
    assert kroger.configured()
    ciphertext=kroger.seal({'access_token':'private'},1)
    assert kroger.unseal(ciphertext,1)=={'access_token':'private'}
    for candidate,user in [(ciphertext,2),(ciphertext[:-5]+'invalid',1)]:
        with pytest.raises(kroger.KrogerError,match='reconnect'):kroger.unseal(candidate,user)


@pytest.mark.parametrize('quantity',[0,-1,100,1.5,True,'2',None,float('nan')])
def test_cart_quantity_rejected_before_network(config,monkeypatch,quantity):
    def unexpected(*args):pytest.fail('Invalid payload must not contact Kroger')
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',unexpected)
    with pytest.raises(kroger.KrogerError,match='invalid'):
        kroger.add_to_cart('token',[dict(upc='0001111040101',quantity=quantity)],'PICKUP')


@pytest.mark.parametrize('zip_code',['', '2290','229033','22A03','22903-1234'])
def test_zip_requires_exactly_five_ascii_digits(config,zip_code):
    with pytest.raises(kroger.KrogerError,match='zip'):kroger.locations('token',zip_code)


def test_cart_size_limit_and_identifier_preserve_leading_zeroes(config,monkeypatch):
    bodies=[]
    def handle(transport,request):
        bodies.append(json.loads(request.content));return httpx.Response(204)
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',handle)
    items=[dict(upc=f'{number:013d}',quantity=1) for number in range(1,51)]
    kroger.add_to_cart('token',items,'DELIVERY')
    assert len(bodies)==1 and len(bodies[0]['items'])==50
    assert bodies[0]['items'][0]==dict(upc='0000000000001',quantity=1,modality='DELIVERY')
    with pytest.raises(kroger.KrogerError,match='invalid'):kroger.add_to_cart('token',items+[items[0]],'DELIVERY')
    assert len(bodies)==1


def test_draft_fingerprint_catches_quantity_change_but_not_item_order():
    items=[dict(key='rice|cup',quantity=2,unit='cup',name='rice'),dict(key='eggs|each',quantity=3,unit='each',name='eggs')]
    assert kroger.fingerprint(1,items)==kroger.fingerprint(1,list(reversed(items)))
    assert kroger.fingerprint(1,items)!=kroger.fingerprint(2,items)
    changed=[dict(item) for item in items];changed[0]['quantity']=3
    assert kroger.fingerprint(1,items)!=kroger.fingerprint(1,changed)
    draft=kroger.new_draft(1,items,dict(id='02900372',modality='PICKUP'),'connection')
    assert all(row['selection'] is None for row in draft['rows'])
    assert draft['expires']>time.time() and draft['state']=='editing'
    with pytest.raises(kroger.KrogerError,match='size'):kroger.new_draft(1,items*51,{},'connection')


@pytest.mark.parametrize('term',['','a'*101,'one two three four five six seven eight nine'])
def test_bad_product_search_never_contacts_provider(config,term):
    with pytest.raises(kroger.KrogerError,match='search'):kroger.products('token','02900372',term)


def test_only_valid_string_upcs_become_candidate_products(config,monkeypatch):
    def handle(transport,request):
        return httpx.Response(200,json={'data':[
            dict(upc=1111040101,description='Numeric identifier loses leading zero'),
            dict(upc='https://evil.test',description='Invalid identifier'),
            dict(upc='0001111040101',description='<script>product</script>',items=[dict(size='16 oz',price={'regular':3,'promo':0})])]})
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',handle)
    products=kroger.products('token','02900372','rice')
    assert len(products)==1 and products[0]['upc']=='0001111040101'
    assert products[0]['price']==3 and products[0]['size']=='16 oz'


def test_json_and_token_errors_do_not_expose_provider_messages(config,monkeypatch):
    def handle(transport,request):return httpx.Response(200,text='private-token-secret')
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',handle)
    with pytest.raises(kroger.KrogerError,match='response'):kroger.exchange('code','verifier')
    def wrong_scope(transport,request):
        return httpx.Response(200,json=dict(access_token='private-token',expires_in=1800,token_type='bearer',scope='product.compact'))
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',wrong_scope)
    with pytest.raises(kroger.KrogerError,match='response'):kroger.exchange('code','verifier')


def test_expired_connection_without_refresh_token_requires_reconnection(config):
    connection=kroger.seal(dict(access_token='private',expires=0,refresh_token=None,connection_id='a'),1)
    with pytest.raises(kroger.KrogerError,match='reconnect'):kroger.access({'kroger_connection':connection},1)
