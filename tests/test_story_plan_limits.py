"""User stories #7-#11: bounded pantry inputs and plan responses."""
import copy
import pytest
from app.services.schema import parse_plan
from app.models import PantryItem
from tests.helpers import signup
from tests.test_plan import good_plan

@pytest.mark.parametrize('change', ['blank_name','blank_step','too_many_meals','too_many_steps','too_many_ingredients','long_step','huge_quantity'])
def test_invalid_plan_structures_are_rejected(change):
    p=copy.deepcopy(good_plan());m=p['meals'][0]
    if change=='blank_name':m['name']='   '
    if change=='blank_step':m['steps']=['   ']
    if change=='too_many_meals':p['meals']=p['meals']*2
    if change=='too_many_steps':m['steps']=['mix']*31
    if change=='too_many_ingredients':m['ingredients']=m['ingredients']*51
    if change=='long_step':m['steps']=['x'*2001]
    if change=='huge_quantity':m['ingredients'][0]['quantity']=1e9
    assert parse_plan(p)[1]


def test_overlong_pantry_unit_is_not_silently_truncated(client):
    signup(client)
    r=client.post('/pantry/add',data={'name':'rice','quantity':'1','unit':'x'*21})
    assert 'Unit must be 20 characters' in r.text
    with client.app.state.session_factory() as db:assert db.query(PantryItem).count()==0


def test_fractional_prep_duration_rejected(client):
    signup(client)
    assert client.post('/survey',data={'budget':'90','prep_present':'1','prep_minutes':'30.9'}).status_code==400
