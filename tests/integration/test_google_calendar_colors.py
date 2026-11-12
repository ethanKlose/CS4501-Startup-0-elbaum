"""Color serialization and safe migration of events already synced to Google."""
import copy
from types import SimpleNamespace

import pytest

from app.services import google_calendar as google
from tests.integration.helpers import generate, onboard, snapshot
from tests.integration.test_google_calendar import google_provider, connect, current_sync

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('category,color_id', [('breakfast','5'),('lunch','10'),('dinner','9'),('prep','3'),('outside','8')])
def test_explicit_plan_category_determines_google_color(google_provider, category, color_id, monkeypatch):
    monkeypatch.setenv('SECRET_KEY','isolated-color-test-secret-over-thirty-two-characters')
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setenv('TIMEZONE','America/New_York')
    # Misleading names must never turn a dinner or outside meal into prep.
    # The real entry builder is tested in the HTTP workflows below.
    monkeypatch.setattr(google, 'entries', lambda plan: [dict(key='stable-slot',category=category,
        day=0,minute=480,duration=30,title='Cook breakfast dinner at the dining hall',description='Recipe')])
    plan=SimpleNamespace(settings={'week_start':'2026-11-16'})
    body=next(iter(google.event_bodies(plan,1).values()))
    assert body['colorId']==color_id
    assert body['summary']=='Cook breakfast dinner at the dining hall'
    assert body['start']['dateTime']=='2026-11-16T08:00:00-05:00'


def test_existing_single_color_events_are_recolored_without_duplicates(application, web, google_provider):
    onboard(web); generate(web); saved=snapshot(application); connect(web)
    assert 'Calendar synced:' in current_sync(web,saved).text
    # Model events created before this update, when no per-event color was set.
    for event in google_provider.events.values():
        event.pop('colorId')
    old=copy.deepcopy(google_provider.events)
    calls=len(google_provider.calls)
    personal=dict(id='personal-event',summary='Class',colorId='11',start={'dateTime':'2026-11-16T10:00:00-05:00'})
    google_provider.events['personal-event']=copy.deepcopy(personal)
    page=current_sync(web,saved)
    assert f"0 added, {len(old)} updated, 0 removed" in page.text
    assert set(google_provider.events)==set(old)|{'personal-event'}
    assert google_provider.events['personal-event']==personal
    for identifier,event in old.items():
        after=google_provider.events[identifier]
        assert after['start']==event['start'] and after['end']==event['end']
        assert after['summary']==event['summary'] and after['description']==event['description']
    changed=google_provider.calls[calls:]
    assert not any(request.method in {'POST','DELETE'} for request in changed)
    meal_colors={}
    for meal in saved['meals']:
        meal_colors.setdefault(meal['slot'],set()).add(google.EVENT_STYLES[meal['slot']]['color_id'])
    assert meal_colors=={'breakfast':{'5'},'lunch':{'10'},'dinner':{'9'}}
    actual=google_provider.events
    for meal in saved['meals']:
        matches=[event for event in actual.values() if event.get('summary')==meal['name'] and event.get('start',{}).get('dateTime','')[11:16]=={'breakfast':'08:00','lunch':'12:30','dinner':'18:30'}[meal['slot']]]
        assert matches and all(event['colorId']==google.EVENT_STYLES[meal['slot']]['color_id'] for event in matches)
    assert any(event.get('summary','').startswith('Cook ') and event['colorId']=='3' for event in actual.values())
    assert '0 added, 0 updated, 0 removed' in current_sync(web,saved).text


def test_color_only_changes_update_one_event_and_leave_other_events_unchanged(application, web, google_provider):
    onboard(web); generate(web); saved=snapshot(application); connect(web); current_sync(web,saved)
    identifier=next(iter(google_provider.events))
    desired=google_provider.events[identifier]['colorId']
    google_provider.events[identifier]['colorId']='11'
    calls=len(google_provider.calls)
    assert '0 added, 1 updated, 0 removed' in current_sync(web,saved).text
    assert google_provider.events[identifier]['colorId']==desired
    mutations=[request for request in google_provider.calls[calls:] if request.method!='GET']
    assert len(mutations)==1 and mutations[0].method=='PATCH'
    assert mutations[0].url.path.endswith('/'+identifier)


def test_connected_apps_explains_the_same_color_categories(web, google_provider):
    onboard(web)
    page=web.get('/integrations')
    assert page.status_code==200 and 'data-testid="google-color-legend"' in page.text
    for style in google.EVENT_STYLES.values():
        assert style['swatch'] in page.text
        from html import escape
        assert escape(style['label']) in page.text
