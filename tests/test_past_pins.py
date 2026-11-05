import datetime as dt
from sqlalchemy import select
from app.models import Plan,Meal
from app.services import planner
from tests.helpers import signup


def test_plan_from_today_archives_past_pins_without_requiring_them(client,monkeypatch):
    today=dt.date(2026,11,9)
    monkeypatch.setattr(planner,'planning_today',lambda:today)
    monkeypatch.setattr(planner,'planning_now',lambda:dt.datetime.combine(today,dt.time(6)))
    signup(client);client.post('/survey',data={'budget':'150'})
    client.post('/plan/generate',data={'start_mode':'today'})
    with client.app.state.session_factory() as db:
        old=db.scalar(select(Plan));original_id=old.id
        m=next(m for m in old.meals if m.day==0 and m.slot=='breakfast');mid=m.id
    client.post(f'/meals/{mid}/pin')
    today=dt.date(2026,11,12)
    monkeypatch.setattr(planner,'planning_now',lambda:dt.datetime.combine(today,dt.time(17)))
    response=client.post('/plan/generate',data={'start_mode':'today'})
    assert 'could not' not in response.text.lower()
    with client.app.state.session_factory() as db:
        plans=list(db.scalars(select(Plan).order_by(Plan.id)))
        assert len(plans)==2 and plans[-1].id!=original_id
        assert all(m.day>=3 for m in plans[-1].meals)
        assert db.get(Meal,mid).pinned and len(plans[0].meals)==21


def test_elapsed_and_new_external_slots_do_not_retain_pins(client,monkeypatch):
    today=dt.date(2026,11,9)
    monkeypatch.setattr(planner,'planning_today',lambda:today)
    monkeypatch.setattr(planner,'planning_now',lambda:dt.datetime.combine(today,dt.time(6)))
    signup(client);client.post('/survey',data={'budget':'150'})
    client.post('/plan/generate',data={'start_mode':'today'})
    with client.app.state.session_factory() as db:
        mids=[m.id for m in db.query(Meal).filter_by(day=0).all() if m.slot in ['breakfast','dinner']]
    for mid in mids:client.post(f'/meals/{mid}/pin')
    client.post('/preferences/lifestyle',data={'equipment':['stove','oven','toaster','blender','fridge','freezer'],'external_0_dinner':'on'})
    monkeypatch.setattr(planner,'planning_now',lambda:dt.datetime.combine(today,dt.time(10)))
    client.post('/plan/generate',data={'start_mode':'today'})
    with client.app.state.session_factory() as db:
        p=db.scalar(select(Plan).order_by(Plan.id.desc()))
        assert db.query(Plan).count()==2
        assert not any(m.day==0 and m.slot in ['breakfast','dinner'] for m in p.meals)
