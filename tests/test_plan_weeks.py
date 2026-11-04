import datetime as dt

from app.models import Meal, Plan
from app.services import planner, weeks
from app.services.weeks import plan_week_start
from tests.helpers import signup


def latest(client):
    with client.app.state.session_factory() as s:
        p = s.query(Plan).order_by(Plan.id.desc()).first()
        return p, list(p.meals)


def test_midweek_generation_has_no_past_prep(client, monkeypatch):
    today = dt.date(2026, 11, 4)
    monkeypatch.setattr(weeks, 'planning_today', lambda: today)
    monkeypatch.setattr(planner, 'planning_today', lambda: today)
    signup(client)
    client.post('/survey', data={'budget': '150'})
    client.post('/plan/generate')
    p, ms = latest(client)
    assert plan_week_start(p) == dt.date(2026, 11, 9)
    assert all(plan_week_start(p) + dt.timedelta(days=m.cook_day) > today for m in ms)
    assert 'Nov 9 – 15, 2026' in client.get('/').text


def test_sunday_generation_does_not_require_prep_earlier_today(client, monkeypatch):
    today = dt.date(2026, 11, 8)
    monkeypatch.setattr(weeks, 'planning_today', lambda: today)
    monkeypatch.setattr(planner, 'planning_today', lambda: today)
    signup(client)
    client.post('/survey', data={'budget': '150'})
    client.post('/plan/generate')
    p, ms = latest(client)
    assert plan_week_start(p) == dt.date(2026, 11, 9)
    assert p.settings['allow_pre_week'] is False
    assert all(m.cook_day >= 0 for m in ms)


def test_next_week_advances_dates_and_clears_one_week_skips(client):
    signup(client)
    client.post('/survey', data={'budget': '150'})
    client.post('/plan/generate')
    first, _ = latest(client)
    client.post('/plan/days/2/skip')
    client.post('/plan/regenerate')
    same, _ = latest(client)
    assert plan_week_start(same) == plan_week_start(first)
    client.post('/plan/next-week')
    following, ms = latest(client)
    assert plan_week_start(following) == plan_week_start(first) + dt.timedelta(days=7)
    assert len(ms) == 21 and not any(d['skipped'] for d in following.days)


def test_future_plan_checkin_banner_waits_for_its_own_weekend():
    from app.routers.checkin import checkin_due
    plan = Plan(status='ok', created_at=dt.datetime(2026, 11, 4), settings={'week_start': '2026-11-09'})
    assert not checkin_due(plan, False, dt.datetime(2026, 11, 7))
    assert not checkin_due(plan, False, dt.datetime(2026, 11, 13))
    assert checkin_due(plan, False, dt.datetime(2026, 11, 14))
