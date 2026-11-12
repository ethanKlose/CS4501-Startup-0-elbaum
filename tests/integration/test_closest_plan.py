"""Production-default goal relaxation through actual routes, DB and calendar."""
import copy
import pytest
from sqlalchemy import select
from app.models import Plan,Profile,PantryItem
from app.services import planner
from app.services.llm import FakeLLM,get_llm
from app.services.types import PlanContext,DayCtx
from app.services.closest_plan import assess,select_plan,PlanningBlocked
from app.services.validators import check_coverage,check_diet,check_cost_integrity
from tests.integration.helpers import onboard,generate,post,snapshot
from tests.integration.test_beta_preferences import complete_form

pytestmark=pytest.mark.integration

@pytest.fixture(autouse=True)
def production_policy(monkeypatch):monkeypatch.setenv('BEST_EFFORT_PLANNING','1')


def test_screenshot_request_replaces_old_calendar_and_reports_actual_goals(application,web):
    onboard(web,budget='75');generate(web);old=snapshot(application)
    assert post(web,'/survey/generate',complete_form(budget='125',protein_target='140',calorie_target='2500')).status_code==303
    new=snapshot(application);assert new['id']!=old['id']
    assert new['budget']==125 and new['settings']['protein_target']==140 and new['settings']['calorie_target']==2500
    assert len(new['meals'])==21 and new['settings']['closest']['budget']==125
    assert new['settings']['closest']['shopping']==new['settings']['checkout_total']
    page=web.get('/').text
    assert 'generator failed' not in page.lower() and 'Preferences saved, but' not in page
    if new['warnings']:assert 'data-testid="closest-plan"' in page and 'Closest available plan' in page
    assert web.get(f'/plans/{old["id"]}').status_code==200


def test_saved_but_not_generated_preferences_are_explicitly_stale(application,web):
    onboard(web);generate(web)
    assert 'data-testid="preferences-changed"' not in web.get('/').text
    post(web,'/survey',{'budget':'125'})
    page=web.get('/').text
    assert 'data-testid="preferences-changed"' in page and 'Previous preferences' in page
    post(web,'/survey/generate',{'budget':'125'})
    assert 'data-testid="preferences-changed"' not in web.get('/').text


def test_provider_failure_falls_back_locally_and_is_attributed(application,web):
    onboard(web);generate(web);old=snapshot(application)
    class Outage:
        name='openai'
        calls=0
        def generate_plan(self,*a,**kw):self.calls+=1;raise RuntimeError('private credential must not leak')
        def interpret_preferences(self,*a,**kw):raise RuntimeError('private credential must not leak')
    provider=Outage();application.app.dependency_overrides[get_llm]=lambda:provider
    post(web,'/survey/generate',{'budget':'125','free_text':'no fish'})
    new=snapshot(application)
    assert new['id']!=old['id'] and provider.calls==1
    assert new['settings']['closest']['source']=='catalog_fallback'
    assert new['settings']['closest']['requested_engine']=='openai'
    page=web.get('/').text
    assert 'private credential' not in page and 'Local fallback:' in page
    assert all(not check_diet({'meals':[meal]},planner.plan_ctx(db_plan(application,new['id']))) for meal in new['meals'])


def db_plan(application,identifier):
    with application.sessions() as db:
        plan=db.get(Plan,identifier);list(plan.meals);return plan


def test_excessive_request_redirects_to_preferences_without_replacing_or_settling(application,web):
    onboard(web);generate(web);old=snapshot(application)
    with application.sessions() as db:
        p=db.scalar(select(Profile));p.budget=25;p.calorie_target=5000;p.goal='calorie_target';db.commit()
    response=post(web,'/plan/regenerate')
    assert response.status_code==303 and response.headers['location']=='/survey'
    assert 'outside the supported planning range' in web.get('/survey').text
    assert snapshot(application)==old


@pytest.mark.parametrize('kind',['malformed','unsafe','unknown_price','missing','tampered_nutrition'])
def test_bad_provider_cannot_bypass_safe_catalog_fallback(application,web,kind):
    onboard(web,restrictions_present='1',restrictions=['vegan'])
    class Bad:
        name='openai'
        def generate_plan(self,ctx,feedback=()):
            raw=FakeLLM().generate_plan(ctx)
            if kind=='malformed':return {'meals':[{'day':99}]}
            if kind=='missing':raw['meals'].pop()
            elif kind=='tampered_nutrition':raw['meals'][0]['protein']=499
            else:
                m=raw['meals'][0];m['ingredients'].append(dict(name='chicken' if kind=='unsafe' else 'unknown powder',quantity=1,unit='oz',section='meat',cost=1));m['cost']+=1
            return raw
    application.app.dependency_overrides[get_llm]=lambda:Bad()
    generate(web);saved=snapshot(application)
    assert len(saved['meals'])==21 and saved['settings']['closest']['source']=='catalog_fallback'
    assert all('chicken' not in i['name'] and 'unknown powder' not in i['name'] for m in saved['meals'] for i in m['ingredients'])


def test_over_budget_candidate_is_reviewable_but_unknown_prices_are_not():
    ctx=PlanContext(budget=30,days=[DayCtx(i,45) for i in range(7)],checkout_budget=True)
    raw=FakeLLM().generate_plan(PlanContext(budget=200,days=ctx.days,checkout_budget=True))
    plan,hard,warnings,report=assess(raw,ctx)
    assert not hard and report['over_budget']>0 and any('over your $30.00 budget' in w for w in warnings)
    assert not check_coverage(plan,ctx) and not check_cost_integrity(plan,ctx)
    bad=copy.deepcopy(raw);bad['meals'][0]['ingredients'][0]['name']='unpriced mystery'
    assert assess(bad,ctx)[1]


def test_diet_incompatible_provider_and_empty_safe_catalog_redirect_cleanly(application,web,monkeypatch):
    onboard(web)
    monkeypatch.setattr('app.services.llm.FakeLLM.generate_plan',lambda *a,**kw:{'meals':[]})
    response=post(web,'/plan/generate')
    assert response.headers['location']=='/survey'
    assert 'No complete plan could be assembled' in web.get('/survey').text
    with application.sessions() as db:assert db.query(Plan).count()==0


def test_changed_plan_recomputes_closest_metrics_after_skip(application,web):
    onboard(web,goal='protein_calorie',protein_target='140',calorie_target='2500',budget='125')
    generate(web);saved=snapshot(application)
    assert post(web,'/plan/days/2/skip').status_code==303
    changed=snapshot(application);details=changed['settings']['closest']
    assert len(changed['meals'])==18 and len(details['days'])==6
    assert details['average_calories']==round(sum(m['calories'] for m in changed['meals'])/6)
    assert details['shopping']==changed['settings']['checkout_total']
    assert details['unique_recipes']==len({m['name'] for m in changed['meals']})
