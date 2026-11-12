"""Real HTTP/auth/CSRF/migrations/database/service, controlled Google HTTP only.

These are deterministic integration tests, not evidence of a live Google consent.
"""
import base64
import copy
import hashlib
import json
import time
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.models import Plan, User
from app.services import google_calendar as google
from app.services.preferences import get_preferences, save_preferences
from tests.integration.helpers import generate, onboard, post, snapshot

pytestmark = pytest.mark.integration


class GoogleTransport:
    def __init__(self):
        self.events = {}
        self.calls = []
        self.refresh = 0
        self.fail_method = None
        self.fail_status = 503
        self.fail_once = False
        self.token_failure = None
        self.conflict = False
        self.page = False

    def handle(self, transport, request):
        self.calls.append(request)
        url, method = str(request.url), request.method
        if url == google.TOKEN_URL:
            form = parse_qs(request.content.decode())
            assert form['client_secret'] == ['google-test-secret']
            if self.token_failure:
                return httpx.Response(400, json={'error': self.token_failure})
            if form['grant_type'] == ['refresh_token']:
                assert form['refresh_token'] == ['test-refresh']
                self.refresh += 1
            else:
                assert form['code_verifier'][0] and form['code'] == ['test-code']
            return httpx.Response(200, json=dict(access_token='test-access', refresh_token='test-refresh',
                expires_in=3600, token_type='Bearer', scope=google.SCOPE))
        if url == 'https://oauth2.googleapis.com/revoke':
            assert parse_qs(request.content.decode())['token'] == ['test-refresh']
            return httpx.Response(200)
        assert url.startswith(google.EVENTS_URL)
        assert request.headers['Authorization'] == 'Bearer test-access'
        if self.fail_method == method:
            if self.fail_once:
                self.fail_method = None
            if self.fail_status == 'timeout':
                raise httpx.ReadTimeout('test-access test-refresh', request=request)
            return httpx.Response(self.fail_status, text='test-access test-refresh')
        if method == 'GET' and request.url.path.endswith('/events'):
            filters = request.url.params.get_list('privateExtendedProperty')
            assert len(filters) == 2
            wanted = dict(f.split('=', 1) for f in filters)
            events = [e for e in self.events.values() if e.get('status') != 'cancelled' and all(e.get('extendedProperties', {}).get('private', {}).get(k) == v for k, v in wanted.items())]
            if self.page and not request.url.params.get('pageToken'):
                return httpx.Response(200, json={'items': events[:1], 'nextPageToken': 'page-2'})
            return httpx.Response(200, json={'items': events[1:] if self.page else events})
        identifier = request.url.path.rsplit('/', 1)[-1]
        if method == 'POST':
            body = json.loads(request.content)
            identifier = body['id']
            if identifier in self.events or self.conflict:
                if self.conflict:
                    self.events[identifier] = dict(body, extendedProperties={'private': {'platejoy_owner': 'someone-else'}})
                    self.conflict = False
                return httpx.Response(409)
            self.events[identifier] = dict(body, etag='"v1"')
            return httpx.Response(200, json=self.events[identifier])
        if method == 'GET':
            return httpx.Response(200, json=self.events[identifier]) if identifier in self.events else httpx.Response(404)
        if method == 'PATCH':
            assert request.headers.get('If-Match') == self.events[identifier]['etag']
            self.events[identifier].update(json.loads(request.content))
            self.events[identifier]['etag'] = '"v2"'
            return httpx.Response(200, json=self.events[identifier])
        if method == 'DELETE':
            assert request.headers.get('If-Match') == self.events[identifier]['etag']
            self.events[identifier]['status'] = 'cancelled'
            return httpx.Response(204)
        pytest.fail(f'Unexpected integration request {method}')


@pytest.fixture
def google_provider(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'google-test-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'google-test-secret')
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', 'http://127.0.0.1:8000/integrations/google/callback')
    monkeypatch.setenv('GOOGLE_TOKEN_ENCRYPTION_KEY', Fernet.generate_key().decode())
    provider = GoogleTransport()
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', lambda transport, request: provider.handle(transport, request))
    return provider


def connect(web):
    response = post(web, '/integrations/google/connect')
    assert response.status_code == 303
    query = parse_qs(httpx.URL(response.headers['location']).query.decode())
    assert query['scope'] == [google.SCOPE]
    callback = web.get('/integrations/google/callback', params={'state': query['state'][0], 'code': 'test-code'})
    assert callback.status_code == 303
    assert 'connected' in web.get('/integrations').text.lower()
    return query


def credentials(application, user_id):
    with application.sessions() as db:
        return get_preferences(db, user_id)


def current_sync(web, saved):
    response = post(web, '/integrations/google/sync', {'plan_id': saved['id']})
    assert response.status_code == 303
    return web.get(response.headers['location'])


def test_consent_uses_state_pkce_and_encrypted_server_side_tokens(application, web, google_provider):
    onboard(web)
    saved_user = None
    with application.sessions() as db:
        saved_user = db.scalar(select(User)).id
    response = post(web, '/integrations/google/connect')
    query = parse_qs(httpx.URL(response.headers['location']).query.decode())
    pending = credentials(application, saved_user)['google_pending']
    verifier = google.unseal(pending['credentials'], saved_user)['verifier']
    assert query['code_challenge'] == [base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()]
    assert query['code_challenge_method'] == ['S256'] and query['access_type'] == ['offline']
    assert verifier not in web.cookies.get('session', '')
    assert web.get('/integrations/google/callback', params={'state': query['state'][0], 'code': 'test-code'}).status_code == 303
    data = credentials(application, saved_user)
    assert 'google_pending' not in data
    assert 'test-access' not in json.dumps(data) and 'test-refresh' not in json.dumps(data)
    assert google.unseal(data['google_connection'], saved_user)['refresh_token'] == 'test-refresh'
    assert 'test-access' not in web.get('/integrations').text
    # Cookies are signed, not encrypted; decode to explicitly inspect contents.
    cookie = web.cookies.get('session').split('.')[0]
    assert 'test-access' not in base64.b64decode(cookie).decode()
    calls = len(google_provider.calls)
    web.get('/integrations/google/callback', params={'state': query['state'][0], 'code': 'test-code'})
    assert len(google_provider.calls) == calls
    assert 'could not be verified' in web.get('/integrations').text


@pytest.mark.parametrize('failure', ['wrong_state', 'expired', 'cancelled', 'invalid_grant', 'different_browser'])
def test_bad_or_cancelled_consent_never_connects(application, web, google_provider, failure):
    onboard(web)
    with application.sessions() as db:
        user_id = db.scalar(select(User)).id
    response = post(web, '/integrations/google/connect')
    query = parse_qs(httpx.URL(response.headers['location']).query.decode())
    state = query['state'][0]
    if failure == 'expired':
        with application.sessions() as db:
            data = get_preferences(db, user_id)
            secret = google.unseal(data['google_pending']['credentials'], user_id)
            secret['expires'] = 0
            data['google_pending']['credentials'] = google.seal(secret, user_id)
            save_preferences(db, user_id, data); db.commit()
    if failure == 'invalid_grant':
        google_provider.token_failure = 'invalid_grant'
    params = {'state': 'wrong' if failure == 'wrong_state' else state, 'code': 'test-code'}
    if failure == 'cancelled':
        params['error'] = 'access_denied'
    if failure == 'different_browser':
        with application.client() as other:
            assert post(other, '/login', {'email': 'integration@example.test', 'password': 'IntegrationPass123!'}).status_code == 303
            assert other.get('/integrations/google/callback', params=params).status_code == 303
    else:
        assert web.get('/integrations/google/callback', params=params).status_code == 303
    assert not credentials(application, user_id).get('google_connection')
    assert len(google_provider.calls) == (1 if failure == 'invalid_grant' else 0)


def test_meals_prep_sync_round_trip_updates_and_removes_only_this_week(application, web, google_provider):
    onboard(web); generate(web)
    saved = snapshot(application)
    connect(web)
    page = current_sync(web, saved)
    assert 'Calendar synced:' in page.text
    events = copy.deepcopy(google_provider.events)
    assert len(events) > 21
    assert sum(not event['summary'].startswith('Cook ') for event in events.values()) == 21
    assert any(event['summary'].startswith('Cook ') for event in events.values())
    with application.sessions() as db:
        desired = google.event_bodies(db.get(Plan, saved['id']), saved['user_id'])
    assert set(events) == set(desired)
    for identifier, event in desired.items():
        assert {k: events[identifier][k] for k in event} == event
    calls = len(google_provider.calls)
    assert '0 added, 0 updated, 0 removed' in current_sync(web, saved).text
    assert len(google_provider.calls) == calls + 1  # Read only on repeated sync.
    # Personal events and earlier weeks survive even when the provider list is maliciously broad.
    google_provider.events['personal'] = {'id': 'personal', 'summary': 'Class'}
    old = copy.deepcopy(next(iter(events.values())))
    old['id'] = 'e' * 64; old['extendedProperties']['private']['platejoy_week'] = '2020-01-06'
    google_provider.events[old['id']] = old
    with application.sessions() as db:
        plan = db.get(Plan, saved['id'])
        meal = plan.meals[0]
        meal.steps = ['Updated recipe instructions']
        plan.meals[-1].status = 'skipped'
        db.commit()
    assert 'Calendar synced:' in current_sync(web, saved).text
    assert any(e.get('description') == 'Updated recipe instructions' for e in google_provider.events.values())
    assert 'personal' in google_provider.events and old['id'] in google_provider.events
    assert any(r.method == 'DELETE' for r in google_provider.calls)
    # Regenerate creates a new plan ID, but meal IDs stay stable by week/day/slot.
    assert post(web, '/plan/regenerate').status_code == 303
    newer = snapshot(application)
    assert newer['id'] != saved['id']
    assert current_sync(web, newer).status_code == 200
    assert sum(not e['summary'].startswith('Cook ') for e in google_provider.events.values() if e.get('status') != 'cancelled' and e.get('extendedProperties', {}).get('private', {}).get('platejoy_week') == newer['settings']['week_start']) == 21


def test_partial_remote_failure_retries_without_duplicates_or_local_plan_changes(application, web, google_provider):
    onboard(web); generate(web); saved = snapshot(application); connect(web)
    original = google_provider.handle
    posts = 0
    def handler(transport, request):
        nonlocal posts
        if request.method == 'POST' and str(request.url).startswith(google.EVENTS_URL):
            posts += 1
            if posts == 3:
                # Simulate a write that succeeded remotely but timed out locally.
                original(transport, request)
                raise httpx.ReadTimeout('test-access', request=request)
        return original(transport, request)
    # Bound methods stored on the instance are explicit transport handlers here.
    import unittest.mock
    with unittest.mock.patch.object(httpx.HTTPTransport, 'handle_request', handler):
        assert 'Some events may already be saved' in current_sync(web, saved).text
    assert len(google_provider.events) == 3
    assert snapshot(application) == saved
    assert 'Calendar synced:' in current_sync(web, saved).text
    with application.sessions() as db:
        assert set(google_provider.events) == set(google.event_bodies(db.get(Plan, saved['id']), saved['user_id']))


@pytest.mark.parametrize('status,phrase', [(401, 'Reconnect'), (403, 'did not allow'), (429, 'limiting requests'), (503, 'Some events'), ('timeout', 'Some events')])
def test_google_errors_are_safe_and_do_not_mutate_plan(application, web, google_provider, status, phrase):
    onboard(web); generate(web); saved = snapshot(application); connect(web)
    google_provider.fail_method = 'GET'; google_provider.fail_status = status
    page = current_sync(web, saved)
    assert phrase in page.text
    assert 'test-access' not in page.text and 'test-refresh' not in page.text
    assert snapshot(application) == saved
    if status == 401:
        assert not credentials(application, saved['user_id']).get('google_connection')


def test_expired_tokens_refresh_and_new_ciphertext_survives_restart(application, web, google_provider):
    onboard(web); generate(web); saved = snapshot(application); connect(web)
    with application.sessions() as db:
        data = get_preferences(db, saved['user_id'])
        tokens = google.unseal(data['google_connection'], saved['user_id']); tokens['expires'] = 0
        data['google_connection'] = google.seal(tokens, saved['user_id'])
        save_preferences(db, saved['user_id'], data); db.commit()
    assert 'Calendar synced:' in current_sync(web, saved).text
    assert google_provider.refresh == 1
    with application.client(cookies=dict(web.cookies)) as restarted:
        assert '0 added, 0 updated, 0 removed' in current_sync(restarted, saved).text
    assert google_provider.refresh == 1


def test_disconnect_revokes_and_removes_tokens_but_leaves_events(application, web, google_provider):
    onboard(web); generate(web); saved = snapshot(application); connect(web); current_sync(web, saved)
    events = copy.deepcopy(google_provider.events)
    assert post(web, '/integrations/google/disconnect').status_code == 303
    data = credentials(application, saved['user_id'])
    assert not any(k in data for k in ('google_connection', 'google_pending', 'google_last_sync'))
    assert google_provider.events == events
    assert str(google_provider.calls[-1].url) == 'https://oauth2.googleapis.com/revoke'
    calls = len(google_provider.calls)
    assert 'Reconnect' in current_sync(web, saved).text
    assert len(google_provider.calls) == calls


def test_foreign_and_stale_plan_ids_and_csrf_are_rejected_before_google(application, web, google_provider):
    onboard(web); generate(web); saved = snapshot(application); connect(web)
    calls = len(google_provider.calls)
    assert web.post('/integrations/google/sync', data={'plan_id': saved['id']}).status_code == 403
    assert post(web, '/integrations/google/sync', {'plan_id': saved['id'] + 100}).status_code == 409
    assert post(web, '/integrations/google/connect', headers={'X-CSRF-Token': 'wrong'}, data={'csrf_token': 'wrong'}).status_code == 403
    with application.client() as other:
        onboard(other, 'other-google@example.test')
        assert post(other, '/integrations/google/sync', {'plan_id': saved['id']}).status_code == 409
    assert len(google_provider.calls) == calls


def test_conflicting_foreign_event_is_never_overwritten(application, web, google_provider):
    onboard(web); generate(web); saved = snapshot(application); connect(web)
    google_provider.conflict = True
    assert 'No unrelated event was changed' in current_sync(web, saved).text
    assert len(google_provider.events) == 1
    assert not any(r.method in ('PATCH', 'DELETE') for r in google_provider.calls)


def test_paginated_events_are_all_reconciled(application, web, google_provider):
    onboard(web); generate(web); saved = snapshot(application); connect(web); current_sync(web, saved)
    google_provider.page = True
    assert '0 added, 0 updated, 0 removed' in current_sync(web, saved).text
    assert google_provider.calls[-1].url.params['pageToken'] == 'page-2'


def test_missing_setup_is_visible_and_has_no_provider_calls(application, web, monkeypatch):
    onboard(web)
    for key in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_TOKEN_ENCRYPTION_KEY'):
        monkeypatch.delenv(key, raising=False)
    assert 'setup is needed' in web.get('/integrations').text
    assert post(web, '/integrations/google/connect').status_code == 303
    assert 'needs local setup' in web.get('/integrations').text


def test_restoring_a_skipped_meal_restores_its_google_tombstone(application, web, google_provider):
    onboard(web); generate(web); saved=snapshot(application); connect(web); current_sync(web,saved)
    meal=saved['meals'][0]
    with application.sessions() as db:
        desired=google.event_bodies(db.get(Plan,saved['id']),saved['user_id'])
    identifier=next(key for key,value in desired.items() if value['summary']==meal['name'] and not value['summary'].startswith('Cook ') and value['start']['dateTime'].startswith(saved['settings']['week_start']))
    assert post(web,f"/meals/{meal['id']}/status",{'status':'skipped'}).status_code==303
    current_sync(web,saved)
    assert google_provider.events[identifier]['status']=='cancelled'
    assert post(web,f"/meals/{meal['id']}/status",{'status':'planned'}).status_code==303
    assert 'Calendar synced:' in current_sync(web,saved).text
    assert google_provider.events[identifier]['status']=='confirmed'
