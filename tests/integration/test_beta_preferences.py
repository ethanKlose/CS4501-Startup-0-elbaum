"""Real migrated database and HTTP flows for the unified Beta planning form."""
import json

import pytest
from sqlalchemy import select

from app.models import Plan, Profile, UserPreference
from app.services.planner import plan_ctx
from app.services.validators import check_goal
from tests.integration.helpers import register, onboard, post, generate, snapshot

pytestmark=pytest.mark.integration


def complete_form(**overrides):
    values=dict(budget='200',goals_present='1',goals=['high_protein','calorie_target'],protein_target='110',calorie_target='2000',
                lifestyle_present='1',equipment=['stove','oven','microwave','toaster','blender','fridge','freezer'],
                cooking_skill='any',schedule_present='1',time_breakfast='08:00',time_lunch='12:30',time_dinner='18:30',
                prep_present='1',prep_style='auto',prep_minutes='120',restrictions_present='1')
    values.update({f'minutes_{day}':'60' for day in range(7)})
    values.update(overrides)
    return values


def test_one_save_reaches_context_calendar_verification_and_regeneration(application,web):
    register(web)
    assert post(web,'/survey',complete_form()).status_code==303
    page=generate(web)
    first=snapshot(application)
    assert (first['settings']['goal'],first['settings']['protein_target'],first['settings']['calorie_target'])==('protein_calorie',110,2000)
    assert first['settings']['meal_times']=={'breakfast':480,'lunch':750,'dinner':1110}
    with application.sessions() as db:
        plan=db.get(Plan,first['id']);ctx=plan_ctx(plan)
        expected=check_goal({'meals':[meal.as_dict() for meal in plan.meals]},ctx)
        assert all(message in plan.warnings for message in expected)
        assert ctx.protein_target==110 and ctx.calorie_target==2000
    generate(web,'/plan/regenerate')
    second=snapshot(application)
    assert second['id']!=first['id'] and second['settings']['protein_target']==110
    assert web.get(f'/plans/{first["id"]}').status_code==200


def test_bad_schedule_rolls_back_every_section_and_preserves_typed_inputs(application,web):
    onboard(web)
    response=post(web,'/survey',complete_form(budget='90',protein_target='137',equipment=['microwave'],windows_0='18:00-17:00'))
    assert response.status_code==400
    assert 'value="137"' in response.text and 'value="18:00-17:00"' in response.text
    assert 'value="microwave" checked' in response.text
    assert 'id="schedule-windows" open' in response.text
    with application.sessions() as db:
        profile=db.scalar(select(Profile))
        assert (profile.budget,profile.goal,profile.protein_target)==(200,'none',None)
        assert db.scalar(select(UserPreference)) is None


def test_single_save_outside_meals_remove_recipes_and_flag_both_targets(application,web):
    register(web)
    assert post(web,'/survey',complete_form(external_2_lunch='on')).status_code==303
    page=generate(web);saved=snapshot(application)
    assert len(saved['meals'])==20
    assert not any(meal['day']==2 and meal['slot']=='lunch' for meal in saved['meals'])
    assert any('cannot be verified' in warning for warning in saved['warnings'])
    assert 'Needs review' in page.text
    calendar=web.get(f'/plans/{saved["id"]}/calendar.ics')
    assert calendar.status_code==200 and 'SUMMARY:Dining hall / eating elsewhere' in calendar.text


def test_new_targets_do_not_rewrite_history_and_can_be_disabled(application,web):
    register(web);assert post(web,'/survey',complete_form()).status_code==303
    generate(web);original=snapshot(application)
    assert post(web,'/survey',{'goals_present':'1'}).status_code==303
    generate(web,'/plan/regenerate');changed=snapshot(application)
    assert (changed['settings']['goal'],changed['settings']['protein_target'],changed['settings']['calorie_target'])==('none',None,None)
    with application.sessions() as db:
        previous=db.get(Plan,original['id'])
        assert previous.settings['protein_target']==110 and previous.settings['calorie_target']==2000
        assert previous.warnings==original['warnings']


def test_credential_free_approved_catalog_adapter_carries_both_targets():
    # Run the production prompt, catalog hydration and validators. Substitute only
    # the external provider response; this is not a live model-quality test.
    from app.services.llm import OpenAILLM
    from app.services.types import DayCtx,PlanContext
    from app.services.validators import validate_full
    ctx=PlanContext(budget=200,days=[DayCtx(day,60) for day in range(7)],goal='protein_calorie',protein_target=137,calorie_target=2150)
    adapter=OpenAILLM.__new__(OpenAILLM);requests=[]
    def ask(system,user,max_tokens):
        payload=json.loads(user);requests.append((system,payload))
        return {'meals':[dict(slot,name=payload['approved_names_by_slot'][slot['slot']][0]) for slot in payload['required_slots']]}
    adapter._ask=ask
    plan=adapter.generate_plan(ctx)
    assert requests[0][1]['context']['protein_target']==137
    assert requests[0][1]['context']['calorie_target']==2150
    assert 'ALL selected nutrition goals together' in requests[0][0]
    parsed,hard,soft=validate_full(plan,ctx)
    assert hard==[] and len(parsed['meals'])==21
    assert all(meal['calories']>0 and meal['protein']>=0 for meal in parsed['meals'])
