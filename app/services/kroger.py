"""Kroger Public APIs: explicit consent, product review and one-shot cart writes.

Fixed HTTPS hosts only. No order/checkout endpoint, LLM calls or automatic cart
retries. An ambiguous response must be resolved by the user in the retailer cart.
"""
import base64
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

BASE = 'https://api.kroger.com/v1'
TOKEN_URL = BASE + '/connect/oauth2/token'
AUTHORIZE_URL = BASE + '/connect/oauth2/authorize'
SCOPES = {'product.compact', 'cart.basic:write'}
MAX_ROWS = 100
MAX_CART_PRODUCTS = 50


class KrogerError(Exception):
    """Safe public code. Never include raw provider errors or credentials."""


def configuration():
    cfg = {key: os.environ.get('KROGER_' + key, '').strip() for key in ('CLIENT_ID','CLIENT_SECRET','REDIRECT_URI')}
    cfg['ENCRYPTION_KEY'] = os.environ.get('KROGER_TOKEN_ENCRYPTION_KEY', '').strip() or os.environ.get('GOOGLE_TOKEN_ENCRYPTION_KEY', '').strip()
    if not all(cfg.values()):
        raise KrogerError('configuration')
    try:
        uri = urlsplit(cfg['REDIRECT_URI'])
        valid = (uri.hostname and not uri.username and not uri.password and not uri.query and not uri.fragment
            and uri.path == '/integrations/kroger/callback'
            and (uri.scheme == 'https' or (not settings.production and uri.scheme == 'http' and uri.hostname in {'127.0.0.1','localhost'})))
        # Accessing port also validates a malformed configured URL.
        uri.port
        Fernet(cfg['ENCRYPTION_KEY'].encode())
        if not valid or len(settings.secret_key) < 32 or settings.secret_key in {'dev-insecure-secret','change-me-in-prod'}:
            raise ValueError()
    except (ValueError, TypeError):
        raise KrogerError('configuration') from None
    return cfg


def configured():
    try:
        configuration()
        return True
    except KrogerError:
        return False


def seal(value, user_id):
    cipher = Fernet(configuration()['ENCRYPTION_KEY'].encode())
    return cipher.encrypt(json.dumps(dict(provider='kroger',user_id=user_id,value=value)).encode()).decode()


def unseal(value, user_id):
    try:
        body = json.loads(Fernet(configuration()['ENCRYPTION_KEY'].encode()).decrypt(value.encode()))
        if body['provider'] != 'kroger' or body['user_id'] != user_id or not isinstance(body['value'],dict):
            raise ValueError()
        return body['value']
    except (InvalidToken, ValueError, TypeError, KeyError, AttributeError):
        raise KrogerError('reconnect') from None


def begin(data, session, user_id):
    cfg = configuration()
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    session['kroger_oauth_state'] = state
    data['kroger_pending'] = dict(state_hash=hashlib.sha256(state.encode()).hexdigest(),
        secret=seal(dict(verifier=verifier,expires=time.time()+600),user_id))
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return AUTHORIZE_URL+'?'+urlencode(dict(client_id=cfg['CLIENT_ID'],redirect_uri=cfg['REDIRECT_URI'],
        response_type='code',scope=' '.join(sorted(SCOPES)),state=state,code_challenge=challenge,code_challenge_method='S256'))


def consume_state(data, session, state, user_id):
    expected = session.pop('kroger_oauth_state','')
    pending = data.pop('kroger_pending',{})
    if (not isinstance(state,str) or not state or len(state)>256 or not expected or not hmac.compare_digest(expected,state)
            or not hmac.compare_digest(pending.get('state_hash',''),hashlib.sha256(state.encode()).hexdigest())):
        raise KrogerError('state')
    value=unseal(pending.get('secret',''),user_id)
    if value.get('expires',0)<time.time():
        raise KrogerError('state')
    return value['verifier']


def json_body(response):
    try:
        if len(response.content)>2_000_000:
            raise ValueError()
        value=response.json()
        if not isinstance(value,dict):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise KrogerError('response') from None


def _token(form, previous=None):
    cfg=configuration()
    try:
        with httpx.Client(timeout=10,follow_redirects=False) as client:
            response=client.post(TOKEN_URL,data=form,auth=httpx.BasicAuth(cfg['CLIENT_ID'],cfg['CLIENT_SECRET']),
                headers={'Accept':'application/json'})
    except httpx.HTTPError:
        raise KrogerError('provider') from None
    if response.status_code in (400,401,403):
        raise KrogerError('reconnect')
    if response.status_code!=200:
        raise KrogerError('provider')
    value=json_body(response)
    try:
        access=value['access_token']; expiry=value['expires_in']; refresh=value.get('refresh_token') or (previous or {}).get('refresh_token')
        if (not isinstance(access,str) or not 1<=len(access)<=8192 or isinstance(expiry,bool)
                or not isinstance(expiry,(int,float)) or not math.isfinite(expiry) or not 1<=expiry<=86400
                or value.get('token_type','').lower()!='bearer'
                or (refresh is not None and (not isinstance(refresh,str) or not 1<=len(refresh)<=8192))
                or (value.get('scope') is not None and not SCOPES.issubset(set(value['scope'].split())))):
            raise ValueError()
        return dict(access_token=access,refresh_token=refresh,expires=time.time()+expiry,
                    connection_id=(previous or {}).get('connection_id') or secrets.token_urlsafe(24))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise KrogerError('response') from None


def exchange(code, verifier):
    cfg=configuration()
    if not code or len(code)>4096:
        raise KrogerError('response')
    return _token(dict(grant_type='authorization_code',code=code,redirect_uri=cfg['REDIRECT_URI'],code_verifier=verifier))


def access(data, user_id):
    if not data.get('kroger_connection'):
        raise KrogerError('reconnect')
    token=unseal(data['kroger_connection'],user_id)
    if token.get('expires',0)<=time.time()+60:
        if not token.get('refresh_token'):
            raise KrogerError('reconnect')
        token=_token(dict(grant_type='refresh_token',refresh_token=token['refresh_token']),token)
        data['kroger_connection']=seal(token,user_id)
    return token['access_token'],token['connection_id']


def request(token, path, params=None):
    # Paths are internal literals only. Validate as defense in depth against SSRF.
    if path not in {'/locations','/products'}:
        raise KrogerError('invalid')
    try:
        with httpx.Client(timeout=10,follow_redirects=False) as client:
            response=client.get(BASE+path,params=params,headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
    except httpx.HTTPError:
        raise KrogerError('provider') from None
    if response.status_code==401:
        raise KrogerError('reconnect')
    if response.status_code==403:
        raise KrogerError('permission')
    if response.status_code==429:
        raise KrogerError('quota')
    if response.status_code!=200:
        raise KrogerError('provider')
    value=json_body(response)
    if not isinstance(value.get('data'),list):
        raise KrogerError('response')
    return value['data']


def locations(token, zip_code):
    if not isinstance(zip_code,str) or not re.fullmatch(r'[0-9]{5}',zip_code):
        raise KrogerError('zip')
    rows=request(token,'/locations',{'filter.zipCode.near':zip_code,'filter.radiusInMiles':'20','filter.limit':'10'})
    result=[]
    for row in rows[:10]:
        if not isinstance(row,dict):
            raise KrogerError('response')
        identifier=row.get('locationId'); address=row.get('address') or {}
        if not isinstance(identifier,str) or not re.fullmatch(r'[0-9]{1,16}',identifier) or not isinstance(address,dict):
            raise KrogerError('response')
        result.append(dict(id=identifier,name=str(row.get('name') or row.get('chain') or 'Kroger store')[:160],
            address=', '.join(str(address.get(field,''))[:100] for field in ('addressLine1','city','state','zipCode') if address.get(field))))
    return result


def product_image(images):
    """Choose a real provider image; never manufacture a product photograph URL."""
    if not isinstance(images,list):
        return None
    candidates=[]
    for image in images[:20]:
        if not isinstance(image,dict) or not isinstance(image.get('sizes'),list):
            continue
        base=(100 if str(image.get('perspective','')).casefold()=='front' else 0)+(20 if image.get('default') is True else 0)
        for size in image['sizes'][:20]:
            if not isinstance(size,dict):continue
            url=size.get('url')
            if not isinstance(url,str) or len(url)>2048 or any(ord(c)<=32 for c in url):continue
            try:
                uri=urlsplit(url)
                host=uri.hostname or ''
                valid=(uri.scheme=='https' and not uri.username and not uri.password and uri.port in (None,443)
                       and (host=='kroger.com' or host.endswith('.kroger.com')))
            except ValueError:
                valid=False
            if valid:
                rank={'medium':50,'large':40,'small':20,'thumbnail':10}.get(str(size.get('size') or size.get('id') or '').casefold(),0)
                candidates.append((base+rank,url))
    return max(candidates,key=lambda item:item[0])[1] if candidates else None


def products(token, location_id, term, modality='PICKUP'):
    if (not isinstance(term,str) or not 1<=len(term.strip())<=100 or len(term.split())>8
            or not isinstance(location_id,str) or not re.fullmatch(r'[0-9]{1,16}',location_id)
            or modality not in {'PICKUP','DELIVERY'}):
        raise KrogerError('search')
    rows=request(token,'/products',{'filter.term':term.strip(),'filter.locationId':location_id,'filter.limit':'5',
        'filter.fulfillment':'csp' if modality=='PICKUP' else 'dth'})
    result=[];seen=set()
    for row in rows[:5]:
        if not isinstance(row,dict):
            raise KrogerError('response')
        upc=row.get('upc'); variants=row.get('items') or []
        if not isinstance(upc,str) or not re.fullmatch(r'[0-9]{8,14}',upc) or not isinstance(variants,list):
            continue  # Do not invent or numerically truncate a retailer identifier.
        if upc in seen:
            continue
        seen.add(upc)
        item=variants[0] if variants and isinstance(variants[0],dict) else {}
        price=item.get('price') or {}; price=price if isinstance(price,dict) else {}
        regular=price.get('regular');promo=price.get('promo')
        def valid_price(value):return not isinstance(value,bool) and isinstance(value,(float,int)) and math.isfinite(value) and 0<value<100_000
        amount=promo if valid_price(promo) else regular if valid_price(regular) else None
        inventory=item.get('inventory') or {}; inventory=inventory if isinstance(inventory,dict) else {}
        available=inventory.get('stockLevel') not in {'OUT_OF_STOCK','TEMPORARILY_OUT_OF_STOCK'}
        result.append(dict(upc=upc,name=str(row.get('description') or 'Kroger product')[:200],
            brand=str(row.get('brand') or '')[:100],size=str(item.get('size') or 'Package size not supplied')[:100],
            price=round(amount,2) if amount is not None else None,available=available,
            image_url=product_image(row.get('images')),sold_by=str(item.get('soldBy') or '')[:40]))
    return result


def fingerprint(plan_id, items):
    values=sorted((i['key'],i['quantity'],i.get('unit','')) for i in items)
    return hashlib.sha256(json.dumps([plan_id,values],sort_keys=True).encode()).hexdigest()


def new_draft(plan_id, items, store, connection_id):
    if not items or len(items)>MAX_ROWS:
        raise KrogerError('size')
    return dict(id=secrets.token_urlsafe(24),plan_id=plan_id,fingerprint=fingerprint(plan_id,items),
        store=dict(store),connection_id=connection_id,expires=time.time()+1800,state='editing',
        rows=[dict(key=i['key'],name=i['name'],quantity=i['quantity'],unit=i.get('unit',''),candidates=[],selection=None) for i in items])


def cart_items(draft):
    merged={}
    for row in draft['rows']:
        chosen=row.get('selection')
        if not chosen:
            continue
        upc=chosen['upc']; quantity=chosen['packages']
        if not isinstance(quantity,int) or isinstance(quantity,bool) or not 1<=quantity<=99:
            raise KrogerError('quantity')
        product=merged.setdefault(upc,dict(upc=upc,quantity=0,name=chosen['name'],size=chosen['size'],price=chosen['price'],ingredients=[]))
        product['quantity']+=quantity;product['ingredients'].append(row['name'])
        if product['quantity']>99:
            raise KrogerError('quantity')
    if not 1<=len(merged)<=MAX_CART_PRODUCTS:
        raise KrogerError('selection')
    return list(merged.values())


def add_to_cart(token, items, modality):
    if modality not in {'PICKUP','DELIVERY'} or not 1<=len(items)<=MAX_CART_PRODUCTS:
        raise KrogerError('invalid')
    body=[]
    for item in items:
        upc=item.get('upc');quantity=item.get('quantity')
        if (not isinstance(upc,str) or not re.fullmatch(r'[0-9]{8,14}',upc) or isinstance(quantity,bool)
                or not isinstance(quantity,int) or not 1<=quantity<=99):
            raise KrogerError('invalid')
        body.append(dict(upc=upc,quantity=quantity,modality=modality))
    # /cart/add is additive despite using PUT. NEVER automatically retry it.
    try:
        with httpx.Client(timeout=12,follow_redirects=False) as client:
            response=client.put(BASE+'/cart/add',json={'items':body},headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
    except httpx.HTTPError:
        raise KrogerError('uncertain') from None
    if response.status_code==204:
        return
    code={400:'rejected',401:'reconnect',403:'permission',404:'rejected',422:'rejected',429:'quota'}.get(response.status_code,'uncertain')
    raise KrogerError(code)
