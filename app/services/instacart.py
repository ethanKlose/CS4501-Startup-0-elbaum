"""Optional shopping-list handoff. Never submits a cart or an order.

Contract: https://docs.instacart.com/developer_platform_api/api/products/create_shopping_list_page
"""
import datetime as dt
import hashlib
import json
import math
import os
from urllib.parse import urlsplit
import httpx

ENDPOINTS = {'development':'https://connect.dev.instacart.tools', 'production':'https://connect.instacart.com'}
UNITS={'each':'each','cup':'cup','tbsp':'tablespoon','tsp':'teaspoon','oz':'ounce'}


class HandoffError(Exception):
    """Safe error code, without provider bodies or credentials."""


def payload(items):
    if not items or len(items)>200:
        raise HandoffError('invalid')
    lines=[]
    for item in items:
        name=item['name'].strip();q=item['quantity'];unit=item.get('unit','').strip().lower()
        if not name or len(name)>100 or not math.isfinite(q) or not 0<q<=1_000_000:
            raise HandoffError('invalid')
        line={'name':name,'display_text':f'{q:g} {unit} {name}'.strip()}
        # Unknown units stay visible; don't pretend that a protein scoop is an item.
        if unit in UNITS:
            line['line_item_measurements']=[{'quantity':q,'unit':UNITS[unit]}]
        lines.append(line)
    return {'title':'PlateJoy weekly groceries','link_type':'shopping_list','expires_in':7,
            'instructions':['Review product matches, package sizes, dietary labels and current store prices before purchasing.'],
            'line_items':lines}


def safe_url(value):
    if not isinstance(value,str) or len(value)>4096 or any(ord(c)<=32 for c in value):return False
    try:
        u=urlsplit(value)
        return (u.scheme=='https' and not u.username and not u.password and u.port in (None,443)
                and (u.hostname=='instacart.com' or (u.hostname or '').endswith('.instacart.com')))
    except ValueError:return False


def create_link(items,cache=None):
    key=os.environ.get('INSTACART_API_KEY','').strip()
    if not key:raise HandoffError('unavailable')
    base=ENDPOINTS.get(os.environ.get('INSTACART_ENV','development'))
    if not base:raise HandoffError('configuration')
    body=payload(items)
    digest=hashlib.sha256((base+json.dumps(body,sort_keys=True)).encode()).hexdigest()
    now=dt.datetime.now(dt.timezone.utc).timestamp()
    if (cache and cache.get('fingerprint')==digest and safe_url(cache.get('url'))
            and isinstance(cache.get('created_at'),(int,float)) and 0<=now-cache['created_at']<6*86400):
        return cache
    try:
        with httpx.Client(timeout=10,follow_redirects=False) as client:
            response=client.post(base+'/idp/v1/products/products_link',json=body,
                headers={'Authorization':'Bearer '+key,'Accept':'application/json'})
        response.raise_for_status()
        value=response.json()
        url=value.get('products_link_url') if isinstance(value,dict) else None
        if not safe_url(url):raise HandoffError('response')
    except (httpx.HTTPError,ValueError):
        raise HandoffError('provider') from None
    return dict(fingerprint=digest,url=url,created_at=now)
