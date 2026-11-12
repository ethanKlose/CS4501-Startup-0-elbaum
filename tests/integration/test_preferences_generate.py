"""Save all preferences and replace the active plan through one real HTTP action."""
import pytest
from sqlalchemy import select
from app.models import Plan,Profile
from app.services.llm import get_llm
from tests.integration.helpers import onboard,generate,post,snapshot
from tests.integration.test_beta_preferences import complete_form

pytestmark=pytest.mark.integration


def test_save_and_generate_uses_new_settings_and_replaces_active_plan(application,web):
    onboard(web);generate(web);old=snapshot(application)
    page=web.get('/survey').text
    assert 'formaction="/survey/generate"' in page
    assert 'Save & generate plan' in page and 'Save only' in page
    result=post(web,'/survey/generate',complete_form(budget='150',protein_target='90',restrictions=['vegetarian']))
    assert result.status_code==303 and result.headers['location']=='/'
    new=snapshot(application)
    assert new['id']!=old['id'] and len(new['meals'])==21
    assert new['budget']==150 and new['settings']['protein_target']==90
    assert new['settings']['calorie_target']==2000 and new['settings']['restrictions']==['vegetarian']
    assert new['settings']['checkout_total']<=150
    assert web.get(f'/plans/{old["id"]}').status_code==200
    assert 'data-preferences-saved="1"' in web.get('/survey').text
    assert 'data-preferences-saved="1"' not in web.get('/survey').text


def test_invalid_preferences_do_not_generate_or_replace_the_plan(application,web,monkeypatch):
    onboard(web);generate(web);old=snapshot(application)
    monkeypatch.setattr('app.services.planner.generate',lambda *a,**kw:pytest.fail('Must validate first'))
    response=post(web,'/survey/generate',complete_form(budget='150',protein_target='137',windows_0='18:00-17:00'))
    assert response.status_code==400 and 'value="137"' in response.text
    assert snapshot(application)==old
    with application.sessions() as db:assert db.scalar(select(Profile)).budget==200


def test_failed_generation_keeps_existing_plan_and_saves_preferences(application,web):
    onboard(web);generate(web);old=snapshot(application)
    class BrokenProvider:
        def generate_plan(self,*args,**kwargs):raise RuntimeError('Provider unavailable')
    application.app.dependency_overrides[get_llm]=lambda:BrokenProvider()
    response=post(web,'/survey/generate',{'budget':'150'})
    assert response.status_code==303
    assert snapshot(application)==old
    with application.sessions() as db:assert db.scalar(select(Profile)).budget==150
    assert 'Preferences saved, but the new plan could not be generated' in web.get('/').text


def test_save_only_does_not_generate(application,web,monkeypatch):
    onboard(web);generate(web);old=snapshot(application)
    monkeypatch.setattr('app.services.planner.generate',lambda *a,**kw:pytest.fail('Save only must not generate'))
    assert post(web,'/survey',{'budget':'150'}).headers['location']=='/survey?saved=1'
    assert snapshot(application)==old


def test_generate_from_preferences_requires_csrf_and_login(application,web):
    onboard(web)
    assert web.post('/survey/generate',data={'budget':'150'}).status_code==403
    with application.sessions() as db:assert db.query(Plan).count()==0
    with application.client() as anonymous:
        result=post(anonymous,'/survey/generate',{'budget':'150'})
        assert result.status_code==303 and result.headers['location']=='/login'


def test_first_plan_is_generated_once_without_onboarding_autosubmit(application,web):
    from tests.integration.helpers import register
    register(web)
    assert post(web,'/survey/generate',complete_form()).status_code==303
    assert len(snapshot(application)['meals'])==21
    assert 'data-autosubmit' not in web.get('/').text
    with application.sessions() as db:assert db.query(Plan).count()==1
