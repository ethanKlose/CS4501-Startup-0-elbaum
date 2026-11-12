"""Explicit, idempotent Google Calendar sync; only PlateJoy-owned events change.

OAuth credentials are encrypted at rest and never put in signed browser cookies.
No LLM requests or automatic background sync occur in this module.
"""
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.services.calendar_export import entries
from app.services.weeks import plan_week_start

SCOPE = 'https://www.googleapis.com/auth/calendar.events.owned'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
EVENTS_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'

# Google Calendar's fixed event palette: Banana, Basil, Blueberry, Grape, Graphite.
# Category comes from the plan slot/type, never recipe-name keyword guessing.
EVENT_STYLES = {
    'breakfast': dict(label='Breakfast', color_id='5', swatch='#f6bf26'),
    'lunch': dict(label='Lunch', color_id='10', swatch='#0b8043'),
    'dinner': dict(label='Dinner', color_id='9', swatch='#3f51b5'),
    'prep': dict(label='Cooking & prep', color_id='3', swatch='#8e24aa'),
    'outside': dict(label='Eating out / dining hall', color_id='8', swatch='#616161'),
}


class CalendarError(Exception):
    """Public error code only; never expose provider bodies or credentials."""


def configuration():
    values = {key: os.environ.get('GOOGLE_' + key, '').strip()
              for key in ('CLIENT_ID', 'CLIENT_SECRET', 'REDIRECT_URI', 'TOKEN_ENCRYPTION_KEY')}
    if not all(values.values()):
        raise CalendarError('configuration')
    try:
        redirect = urlsplit(values['REDIRECT_URI'])
        valid = (not redirect.username and not redirect.password and not redirect.query and not redirect.fragment
                 and redirect.path == '/integrations/google/callback'
                 and (redirect.scheme == 'https' or
                      (not settings.production and redirect.scheme == 'http' and redirect.hostname in {'127.0.0.1', 'localhost'})))
        Fernet(values['TOKEN_ENCRYPTION_KEY'].encode())
        if not valid or settings.secret_key in {'dev-insecure-secret', 'change-me-in-prod'} or len(settings.secret_key) < 32:
            raise ValueError()
    except (ValueError, TypeError):
        raise CalendarError('configuration') from None
    return values


def configured():
    try:
        configuration()
        return True
    except CalendarError:
        return False


def seal(value, user_id):
    cipher = Fernet(configuration()['TOKEN_ENCRYPTION_KEY'].encode())
    return cipher.encrypt(json.dumps({'user_id': user_id, 'value': value}).encode()).decode()


def unseal(value, user_id):
    try:
        cipher = Fernet(configuration()['TOKEN_ENCRYPTION_KEY'].encode())
        body = json.loads(cipher.decrypt(value.encode()))
        if body['user_id'] != user_id or not isinstance(body['value'], dict):
            raise ValueError()
        return body['value']
    except (InvalidToken, ValueError, TypeError, KeyError, AttributeError):
        raise CalendarError('reconnect') from None


def begin(data, session, user_id):
    cfg = configuration()
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    session['google_oauth_state'] = state
    data['google_pending'] = dict(state_hash=hashlib.sha256(state.encode()).hexdigest(),
        credentials=seal(dict(verifier=verifier, expires=time.time() + 600), user_id))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(dict(
        client_id=cfg['CLIENT_ID'], redirect_uri=cfg['REDIRECT_URI'], response_type='code', scope=SCOPE,
        state=state, access_type='offline', prompt='consent select_account', code_challenge=challenge,
        code_challenge_method='S256'))


def consume_state(data, session, state, user_id):
    expected = session.pop('google_oauth_state', '')
    pending = data.pop('google_pending', {})
    if (not isinstance(state, str) or not state or len(state) > 256 or not expected
            or not hmac.compare_digest(state, expected)
            or not hmac.compare_digest(hashlib.sha256(state.encode()).hexdigest(), pending.get('state_hash', ''))):
        raise CalendarError('state')
    secret = unseal(pending.get('credentials', ''), user_id)
    if secret.get('expires', 0) < time.time():
        raise CalendarError('state')
    return secret['verifier']


def _tokens(response, previous=None):
    if response.status_code == 400:
        try:
            if response.json().get('error') == 'invalid_grant':
                raise CalendarError('reconnect')
        except (ValueError, AttributeError):
            pass
    if response.status_code != 200:
        raise CalendarError('provider')
    try:
        value = response.json()
        access, refresh = value['access_token'], value.get('refresh_token') or (previous or {}).get('refresh_token')
        expiry = value['expires_in']
        if (not isinstance(access, str) or not 1 <= len(access) <= 8192
                or not isinstance(refresh, str) or not 1 <= len(refresh) <= 8192
                or not isinstance(expiry, (int, float)) or not 1 <= expiry <= 86400
                or value.get('token_type', '').lower() != 'bearer'
                or (value.get('scope') is not None and SCOPE not in value['scope'].split())):
            raise ValueError()
        return dict(access_token=access, refresh_token=refresh, expires=time.time() + expiry)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CalendarError('response') from None


def exchange(code, verifier):
    cfg = configuration()
    if not code or len(code) > 4096:
        raise CalendarError('response')
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            return _tokens(client.post(TOKEN_URL, data=dict(client_id=cfg['CLIENT_ID'],
                client_secret=cfg['CLIENT_SECRET'], redirect_uri=cfg['REDIRECT_URI'],
                grant_type='authorization_code', code=code, code_verifier=verifier)))
    except httpx.HTTPError:
        raise CalendarError('provider') from None


def access_token(data, user_id):
    cfg = configuration()
    if not data.get('google_connection'):
        raise CalendarError('reconnect')
    token = unseal(data['google_connection'], user_id)
    if token.get('expires', 0) > time.time() + 60:
        return token['access_token']
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            refreshed = _tokens(client.post(TOKEN_URL, data=dict(client_id=cfg['CLIENT_ID'],
                client_secret=cfg['CLIENT_SECRET'], grant_type='refresh_token', refresh_token=token['refresh_token'])), token)
    except httpx.HTTPError:
        raise CalendarError('provider') from None
    data['google_connection'] = seal(refreshed, user_id)
    return refreshed['access_token']


def owner_tag(user_id):
    key = configuration()['TOKEN_ENCRYPTION_KEY'].encode()
    return hmac.new(key, f'platejoy-calendar-v1:{user_id}'.encode(), hashlib.sha256).hexdigest()


def event_bodies(plan, user_id):
    start, zone = plan_week_start(plan), ZoneInfo(settings.timezone)
    owner, week = owner_tag(user_id), start.isoformat()
    result = {}
    for row in entries(plan):
        begins = dt.datetime.combine(start + dt.timedelta(days=row['day']), dt.time(), tzinfo=zone) + dt.timedelta(minutes=row['minute'])
        # Add wall-clock duration before applying the date's UTC offset (DST safe).
        ends = begins + dt.timedelta(minutes=row['duration'])
        event_id = hashlib.sha256(f"{owner}:{week}:{row['key']}".encode()).hexdigest()
        result[event_id] = dict(id=event_id, status='confirmed', summary=row['title'], description=row['description'],
            colorId=EVENT_STYLES[row['category']]['color_id'],
            start=dict(dateTime=begins.isoformat(), timeZone=str(zone)),
            end=dict(dateTime=ends.isoformat(), timeZone=str(zone)),
            extendedProperties=dict(private=dict(platejoy_owner=owner, platejoy_week=week)))
    return result


def sync(plan, user_id, token):
    """Reconcile just this week, preserving other weeks and personal events.

    Fetch-before-write and stable IDs recover from partial requests. Deletes run
    only after every desired event is present. A failure can leave partial remote
    work; retry is safe. No local meal/inventory records are changed.
    """
    desired = event_bodies(plan, user_id)
    owner, week = owner_tag(user_id), plan_week_start(plan).isoformat()
    stats = dict(created=0, updated=0, deleted=0, unchanged=0)
    deadline = time.monotonic() + 55
    calls = 0
    with httpx.Client(headers={'Authorization': 'Bearer ' + token}, timeout=8, follow_redirects=False) as client:
        def request(method, url=EVENTS_URL, **kwargs):
            nonlocal calls
            calls += 1
            remaining = deadline - time.monotonic()
            if calls > 100 or remaining <= 0:
                raise CalendarError('partial')
            try:
                response = client.request(method, url, timeout=min(8, remaining), **kwargs)
            except httpx.HTTPError:
                raise CalendarError('partial') from None
            if response.status_code == 401:
                raise CalendarError('reconnect')
            if response.status_code == 403:
                raise CalendarError('permission')
            if response.status_code == 429:
                raise CalendarError('quota')
            if response.status_code >= 500 or response.is_redirect:
                raise CalendarError('partial')
            return response

        def body(response):
            try:
                value = response.json()
                if not isinstance(value, dict):
                    raise ValueError()
                return value
            except ValueError:
                raise CalendarError('response') from None

        def owns(event):
            properties = event.get('extendedProperties')
            private = properties.get('private') if isinstance(properties, dict) else None
            return isinstance(private, dict) and private.get('platejoy_owner') == owner and private.get('platejoy_week') == week

        existing, page = {}, None
        for _ in range(5):
            params = [('privateExtendedProperty', 'platejoy_owner=' + owner),
                      ('privateExtendedProperty', 'platejoy_week=' + week), ('maxResults', '250')]
            if page:
                params.append(('pageToken', page))
            response = request('GET', params=params)
            if response.status_code != 200:
                raise CalendarError('partial')
            value = body(response)
            items = value.get('items', [])
            if not isinstance(items, list):
                raise CalendarError('response')
            for event in items:
                if isinstance(event, dict) and owns(event) and event.get('status') != 'cancelled':
                    identifier = event.get('id', '')
                    if not isinstance(identifier, str) or len(identifier) != 64 or any(c not in '0123456789abcdef' for c in identifier):
                        raise CalendarError('response')
                    existing[identifier] = event
            page = value.get('nextPageToken')
            if not page:
                break
        else:
            raise CalendarError('partial')

        for identifier, event in desired.items():
            previous = existing.get(identifier)
            if previous is None:
                response = request('POST', json=event, params={'sendUpdates': 'none'})
                if response.status_code == 409:
                    fetched = request('GET', EVENTS_URL + '/' + identifier)
                    if fetched.status_code != 200 or not owns(body(fetched)):
                        raise CalendarError('collision')
                    previous = body(fetched)
                elif response.status_code in (200, 201):
                    saved = body(response)
                    if saved.get('id') != identifier or not owns(saved):
                        raise CalendarError('response')
                    stats['created'] += 1
                    continue
                else:
                    raise CalendarError('partial')
            # Google normalizes dateTime offsets and can omit redundant timeZone.
            def same_time(left, right):
                try:
                    return dt.datetime.fromisoformat(left['dateTime'].replace('Z', '+00:00')) == dt.datetime.fromisoformat(right['dateTime'])
                except (KeyError, ValueError, TypeError):
                    return False
            if (previous.get('status') != 'cancelled' and previous.get('summary') == event['summary'] and previous.get('description', '') == event['description']
                    and previous.get('colorId') == event['colorId']
                    and same_time(previous.get('start', {}), event['start']) and same_time(previous.get('end', {}), event['end'])):
                stats['unchanged'] += 1
                continue
            headers = {'If-Match': previous['etag']} if previous.get('etag') else {}
            response = request('PATCH', EVENTS_URL + '/' + identifier, json={k: v for k, v in event.items() if k != 'id'},
                               headers=headers, params={'sendUpdates': 'none'})
            if response.status_code != 200:
                raise CalendarError('partial')
            saved = body(response)
            if saved.get('id') != identifier or not owns(saved):
                raise CalendarError('response')
            stats['updated'] += 1
        for identifier, previous in existing.items():
            if identifier in desired:
                continue
            headers = {'If-Match': previous['etag']} if previous.get('etag') else {}
            response = request('DELETE', EVENTS_URL + '/' + identifier, headers=headers, params={'sendUpdates': 'none'})
            if response.status_code not in (204, 404, 410):
                raise CalendarError('partial')
            stats['deleted'] += 1
    return stats
