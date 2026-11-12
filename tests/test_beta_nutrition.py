"""Custom amounts, simultaneous goals and preserved legacy semantics."""
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text, inspect
from alembic import command
from alembic.config import Config

from app.db import make_engine
from app.models import Profile, UserPreference
from app.services.nutrition_goals import protein_target
from app.services.planner import plan_ctx
from app.services.types import DayCtx, PlanContext
from app.services.validators import check_goal
from tests.helpers import signup


def saved(client):
    with client.app.state.session_factory() as db:
        return db.scalar(select(Profile))


def goals(**changes):
    return dict(goals_present='1', goals=['high_protein','calorie_target'],
                protein_target='120', calorie_target='2200', **changes)


def test_both_targets_survive_save_reload_and_plain_english_readback(client):
    signup(client)
    response=client.post('/survey',data={'budget':'150',**goals()})
    assert response.status_code==200
    row=saved(client)
    assert (row.goal,row.protein_target,row.calorie_target)==('protein_calorie',120,2200)
    html=client.get('/survey').text
    assert 'value="high_protein" checked' in html and 'value="calorie_target" checked' in html
    assert 'at least 120g protein a day' in html and 'about 2200 calories a day' in html
    assert '<em>beta</em>' in html and '<em>alpha</em>' not in html


@pytest.mark.parametrize('target',['20','75','125','300'])
def test_custom_protein_boundaries_and_integer_steps_are_saved(client,target):
    signup(client)
    response=client.post('/survey',data={'goals_present':'1','goals':'high_protein','protein_target':target})
    assert response.status_code==200
    assert saved(client).protein_target==int(target)


@pytest.mark.parametrize('bad',['','0','19','301','75.5','nan','inf','1e999','-1','abc'])
def test_invalid_protein_rejects_entire_edit_and_keeps_both_goals(client,bad):
    signup(client);client.post('/survey',data={'budget':'150',**goals()})
    data=goals();data.update(protein_target=bad,budget='50',lifestyle_present='1',equipment=['microwave'])
    response=client.post('/survey',data=data)
    assert response.status_code==400 and 'daily protein target' in response.text
    row=saved(client)
    assert (row.budget,row.protein_target,row.calorie_target)==(150,120,2200)
    with client.app.state.session_factory() as db:
        assert db.scalar(select(UserPreference)) is None


def test_invalid_calories_preserve_typed_protein_equipment_and_schedule_in_error_view(client):
    signup(client)
    data=goals();data.update(calorie_target='100',protein_target='137',lifestyle_present='1',equipment=['microwave'],schedule_present='1',windows_0='17:00-18:00')
    response=client.post('/survey',data=data)
    assert response.status_code==400
    assert 'value="137"' in response.text and 'value="17:00-18:00"' in response.text
    assert 'value="microwave" checked' in response.text
    assert 'value="stove" checked' not in response.text
    assert saved(client) is None


@pytest.mark.parametrize('chosen,expected',[(None,('none',None,None)),('high_protein',('high_protein',120,None)),('calorie_target',('calorie_target',None,2200))])
def test_each_target_can_be_removed_independently(client,chosen,expected):
    signup(client);client.post('/survey',data=goals())
    data=goals()
    if chosen is None:data.pop('goals')
    else:data['goals']=chosen
    assert client.post('/survey',data=data).status_code==200
    row=saved(client)
    assert (row.goal,row.protein_target,row.calorie_target)==expected


def test_budget_only_update_keeps_targets_and_unknown_goal_is_rejected(client):
    signup(client);client.post('/survey',data=goals())
    assert client.post('/survey',data={'budget':'90'}).status_code==200
    assert saved(client).protein_target==120
    assert client.post('/survey',data={'goals_present':'1','goals':['high_protein','made_up']}).status_code==400
    assert saved(client).goal=='protein_calorie'


def meal(day,calories,protein):
    return dict(day=day,calories=calories,protein=protein)


def test_validator_reports_both_missed_targets_in_one_pass():
    ctx=PlanContext(budget=200,days=[],goal='protein_calorie',protein_target=120,calorie_target=2000)
    issues=check_goal({'meals':[meal(0,1000,50)]},ctx)
    assert any('calories' in item for item in issues)
    assert any('protein' in item.lower() and '120g' in item for item in issues)


@pytest.mark.parametrize('calories,protein,issue',[(2000,119,'protein'),(1000,130,'calories'),(2000,120,None)])
def test_meeting_one_target_never_suppresses_the_other(calories,protein,issue):
    ctx=PlanContext(budget=200,days=[],goal='protein_calorie',protein_target=120,calorie_target=2000)
    issues=check_goal({'meals':[meal(0,calories,protein)]},ctx)
    assert bool(issues)==bool(issue)
    if issue:assert any(issue in item.lower() for item in issues)


def test_high_average_does_not_hide_a_day_below_custom_protein_target():
    ctx=PlanContext(budget=200,days=[],goal='high_protein',protein_target=120)
    issues=check_goal({'meals':[meal(0,2000,80),meal(1,2000,200)]},ctx)
    assert any('Monday' in item and '120g' in item for item in issues)
    assert not any('Average protein' in item for item in issues)


def test_external_meals_keep_both_full_day_targets_unverifiable():
    ctx=PlanContext(budget=200,days=[],goal='protein_calorie',protein_target=120,calorie_target=2000,external_slots=[{'day':0,'slot':'lunch'}])
    assert 'cannot be verified' in check_goal({'meals':[meal(0,2000,150)]},ctx)[0]


def test_legacy_plans_keep_their_75g_target_without_a_schema_key():
    plan=SimpleNamespace(budget=200,days=[{'weekday':0,'minutes':45}],settings={'goal':'high_protein'})
    ctx=plan_ctx(plan)
    assert ctx.protein_target is None and protein_target(ctx)==75
    assert check_goal({'meals':[meal(0,2000,75)]},ctx)==[]


def test_upgrade_preserves_legacy_profile_and_plan_snapshot_and_runs_twice(tmp_path):
    engine=make_engine('sqlite:///'+str(tmp_path/'beta-upgrade.db'))
    config=Config('alembic.ini')
    with engine.begin() as connection:
        config.attributes['connection']=connection;command.upgrade(config,'0001_baseline')
        connection.execute(text("INSERT INTO users VALUES (1,'legacy@test','hash','2026-11-01')"))
        connection.execute(text("INSERT INTO profiles VALUES (1,1,90,'[]','high_protein',NULL,1,'auto','[]',120,'','{}')"))
        connection.execute(text("INSERT INTO plans VALUES (1,1,'2026-11-01','ok','',1,90,80,1,'[]','{\"goal\":\"high_protein\"}','[]')"))
        command.upgrade(config,'head');command.upgrade(config,'head')
        row=connection.execute(text('SELECT goal,protein_target,budget FROM profiles')).one()
        assert row==('high_protein',None,90)
        assert connection.execute(text('SELECT settings FROM plans')).scalar()=='{"goal":"high_protein"}'
        assert 'protein_target' in {c['name'] for c in inspect(connection).get_columns('profiles')}
