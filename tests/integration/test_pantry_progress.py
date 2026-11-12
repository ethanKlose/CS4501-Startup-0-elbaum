"""Real routes/middleware/database; fragment updates must not save draft settings."""
import pytest
from sqlalchemy import select
from app.models import PantryItem,Profile,Plan
from app.services.planner import plan_ctx
from app.services.pricing import plan_checkout
from tests.integration.helpers import onboard,post,generate,snapshot

pytestmark=pytest.mark.integration
JSON={'Accept':'application/json'}


def test_pantry_add_and_delete_return_escaped_fragments_without_changing_preferences(application,web):
    onboard(web)
    response=post(web,'/pantry/add',dict(name='<script>rice</script>',quantity='2',unit='cup'),headers=JSON)
    assert response.status_code==200 and response.json()['ok']
    body=response.json()['html'];assert '&lt;script&gt;' in body and '<script>' not in body
    assert 'data-pantry-form' in body and 'id="wizard"' not in body
    assert response.headers['cache-control']=='no-store'
    with application.sessions() as db:
        item=db.scalar(select(PantryItem));assert db.scalar(select(Profile)).budget==200
        identifier=item.id
    response=post(web,f'/pantry/{identifier}/delete',headers=JSON)
    assert response.status_code==200 and 'Nothing yet.' in response.json()['html']
    with application.sessions() as db:assert db.query(PantryItem).count()==0


@pytest.mark.parametrize('data',[dict(name=''),dict(name='rice',quantity='nan'),dict(name='rice',quantity='-1'),dict(name='rice',unit='x'*21)])
def test_bad_async_pantry_input_is_an_error_response_and_preserves_saved_state(application,web,data):
    onboard(web);post(web,'/pantry/add',dict(name='rice',quantity='2',unit='cup'))
    response=post(web,'/pantry/add',data,headers=JSON)
    assert response.status_code==400 and not response.json()['ok']
    with application.sessions() as db:
        assert db.query(PantryItem).count()==1
        assert db.scalar(select(PantryItem)).quantity==2
        assert db.scalar(select(Profile)).budget==200


def test_async_pantry_requires_csrf_and_hides_foreign_items(application,web):
    from tests.integration.helpers import register
    onboard(web);post(web,'/pantry/add',dict(name='rice'))
    with application.sessions() as db:identifier=db.scalar(select(PantryItem)).id
    assert web.post('/pantry/add',data={'name':'bad'},headers=JSON).status_code==403
    with application.client() as other:
        register(other,'other-review@example.test')
        response=post(other,f'/pantry/{identifier}/delete',headers=JSON)
        assert response.status_code==404 and 'rice' not in response.text
        response=other.get('/pantry',headers=JSON)
        assert response.status_code==200 and 'Nothing yet.' in response.json()['html']
    with application.sessions() as db:assert db.get(PantryItem,identifier)


def test_pantry_changes_do_not_invalidate_an_unsaved_preferences_draft_version(application,web):
    import re
    onboard(web);before=web.get('/survey').text
    version=re.search('data-preferences-version="([^"]+)"',before)[1]
    post(web,'/pantry/add',dict(name='rice',quantity='2',unit='cup'),headers=JSON)
    assert version in web.get('/survey').text
    assert post(web,'/survey',dict(budget='125')).status_code==303
    assert version not in web.get('/survey').text


def test_shopping_budget_card_and_snapshot_recompute_after_a_day_is_removed(application,web):
    onboard(web);generate(web);saved=snapshot(application)
    assert 'Estimated whole-package shopping total' in web.get('/').text
    assert post(web,'/plan/days/2/skip').status_code==303
    with application.sessions() as db:
        plan=db.get(Plan,saved['id']);ctx=plan_ctx(plan)
        expected,_=plan_checkout([m.as_dict() for m in plan.meals],ctx.pantry,ctx.price_offers)
        assert plan.settings['checkout_total']==expected
        assert plan.settings['quality']['recipes']==len({m.name for m in plan.meals})
    assert f'${expected:.2f}' in web.get('/').text
