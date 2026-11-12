"""Calendar/Instacart boundary and format checks, with no remote I/O."""
import copy
import datetime as dt
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from app.services import google_calendar as google
from app.services.calendar_export import entries, export
from app.services.instacart import payload, HandoffError


@pytest.fixture
def google_config(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'a-unique-long-secret-for-this-test-only')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'unit-client')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'unit-secret')
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', 'http://127.0.0.1:8000/integrations/google/callback')
    monkeypatch.setenv('GOOGLE_TOKEN_ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('TIMEZONE', 'America/New_York')


@pytest.mark.parametrize('uri', ['http://example.test/integrations/google/callback', 'https://example.test/wrong',
    'https://u:p@example.test/integrations/google/callback', 'https://example.test/integrations/google/callback?redirect=evil',
    'https://example.test/integrations/google/callback#fragment'])
def test_oauth_redirect_rejects_insecure_or_ambiguous_configuration(google_config, monkeypatch, uri):
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', uri)
    assert not google.configured()


def test_weak_session_secret_and_missing_encryption_key_disable_oauth(google_config, monkeypatch):
    assert google.configured()
    monkeypatch.setenv('SECRET_KEY', 'change-me-in-prod')
    assert not google.configured()
    monkeypatch.setenv('SECRET_KEY', 'test-session-secret-over-thirty-two-characters')
    monkeypatch.setenv('GOOGLE_TOKEN_ENCRYPTION_KEY', 'not-a-fernet-key')
    assert not google.configured()


def test_encrypted_credentials_are_bound_to_user_and_detect_tampering(google_config):
    ciphertext = google.seal({'access_token': 'private'}, 1)
    assert google.unseal(ciphertext, 1) == {'access_token': 'private'}
    for value, user_id in [(ciphertext, 2), (ciphertext[:-4]+'abcd', 1)]:
        with pytest.raises(google.CalendarError, match='reconnect'):
            google.unseal(value, user_id)


@pytest.mark.parametrize('value', [None, '', {}, {'access_token':'abc'}, {'access_token':'abc','refresh_token':'def','expires_in':0,'token_type':'Bearer'},
    {'access_token':'abc','refresh_token':'def','expires_in':3600,'token_type':'Bearer','scope':'other'}])
def test_malformed_google_token_payload_cannot_connect(value):
    import httpx
    with pytest.raises(google.CalendarError, match='response'):
        google._tokens(httpx.Response(200, json=value))


def example_plan():
    class Meal(SimpleNamespace):
        def as_dict(self):
            return {key: getattr(self,key) for key in ['day','slot','name','cook_minutes','steps']}
    active = Meal(id=1, day=6, slot='dinner', name='Chicken, rice; vegetables', cook_minutes=20,
                  steps=['Cook safely.\nServe.'], cook_day=-1, frozen=True, status='planned')
    return SimpleNamespace(id=1, settings={'week_start':'2026-10-26'}, meals=[active])


def test_calendar_dates_use_each_days_dst_offset_and_ids_survive_regeneration(google_config):
    plan = example_plan()
    result = google.event_bodies(plan, 5)
    assert len(result) == 2
    dinner = next(e for e in result.values() if not e['summary'].startswith('Cook '))
    prep = next(e for e in result.values() if e['summary'].startswith('Cook '))
    assert dinner['start']['dateTime'] == '2026-11-01T18:30:00-05:00'
    assert prep['start']['dateTime'] == '2026-10-25T10:00:00-04:00'
    assert all(len(key)==64 and set(key)<=set('0123456789abcdef') for key in result)
    plan.id=900; plan.meals[0].id=9000
    assert set(google.event_bodies(plan, 5)) == set(result)
    assert set(google.event_bodies(plan, 6)).isdisjoint(result)
    plan.settings['week_start']='2026-11-02'
    assert set(google.event_bodies(plan, 5)).isdisjoint(result)


def test_skipped_meals_remove_their_prep_blocks_from_both_calendars(google_config):
    plan = example_plan(); assert len(entries(plan)) == 2
    plan.meals[0].status='skipped'
    assert entries(plan) == []
    assert google.event_bodies(plan, 5) == {}
    assert 'BEGIN:VEVENT' not in export(plan)


def test_calendar_includes_outside_meals_but_not_past_slots(google_config):
    plan=example_plan(); plan.meals=[]
    plan.settings['external_slots']=[dict(day=0,slot='lunch',source='Dining hall'),dict(day=1,slot='lunch',source='Old meal',past=True)]
    assert [e['title'] for e in entries(plan)] == ['Dining hall']
    result=google.event_bodies(plan, 1)
    assert len(result)==1
    assert next(iter(result.values()))['start']['dateTime']=='2026-10-26T12:30:00-04:00'


@pytest.mark.parametrize('quantity', [None, '1', True, -1, 0, float('nan'), float('inf'), 1_000_001])
def test_instacart_quantity_boundary_rejects_invalid_values(quantity):
    with pytest.raises(HandoffError, match='invalid'):
        payload([dict(name='rice',quantity=quantity,unit='cup')])


def test_instacart_size_limit_and_measurements_are_explicit():
    item=dict(name='rice',quantity=1,unit='cup')
    assert len(payload([item]*200)['line_items'])==200
    with pytest.raises(HandoffError, match='invalid'):
        payload([item]*201)
    rows=payload([item,dict(name='protein powder',quantity=2,unit='scoop')])['line_items']
    assert rows[0]['line_item_measurements']==[dict(quantity=1,unit='cup')]
    assert rows[1]['display_text']=='2 scoop protein powder'
    assert 'line_item_measurements' not in rows[1]
