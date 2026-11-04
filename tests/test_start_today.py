import datetime as dt
from app.services import planner, weeks
from app.models import Plan
from tests.helpers import signup


def test_start_today_never_schedules_past_meals_or_cooking(client,monkeypatch):
    now=dt.datetime(2026,11,4,10,0)
    monkeypatch.setattr(planner,'planning_today',lambda:now.date())
    monkeypatch.setattr(planner,'planning_now',lambda:now)
    monkeypatch.setattr(weeks,'planning_today',lambda:now.date())
    signup(client);client.post('/survey',data={'budget':'150'})
    client.post('/plan/generate',data={'start_mode':'today'})
    with client.app.state.session_factory() as s:
        p=s.query(Plan).first()
        assert p and p.settings['earliest_day']==2
        assert all(m.day>=2 for m in p.meals)
        assert not any(m.day==2 and m.slot=='breakfast' for m in p.meals)
        assert all(m.cook_day>=2 for m in p.meals)
