"""Regression checks for user stories #2-#6; manual cases live in docs/manual/."""
import pytest
from app.routers.survey import parse_minutes
from app.services.preference_text import interpret
from app.services.diet import meal_violations
from tests.helpers import signup
from app.models import Profile

@pytest.mark.parametrize('raw', ['0.5','15.9','nan','inf','-1','481'])
def test_minutes_reject_invalid_or_fractional_values(raw):
    assert parse_minutes(raw) is None

@pytest.mark.parametrize('raw,want', [('0',0),('480',480),('45.0',45)])
def test_minutes_accept_integer_boundaries(raw,want):
    assert parse_minutes(raw)==want


def test_unknown_diet_does_not_silently_clear_saved_restrictions(client):
    signup(client)
    client.post('/survey',data={'budget':'90','restrictions_present':'1','restrictions':'vegan'})
    r=client.post('/survey',data={'restrictions_present':'1','restrictions':'made_up'})
    assert r.status_code==400 and 'Choose dietary restrictions' in r.text
    with client.app.state.session_factory() as db:
        assert db.query(Profile).first().restrictions==['vegan']


def test_fractional_calorie_goal_is_not_rounded(client):
    signup(client)
    assert client.post('/survey',data={'budget':'90','goal':'calorie_target','calorie_target':'1200.9'}).status_code==400

@pytest.mark.parametrize('text',['I only eat chicken','Chicken is the only meat I eat','I eat chicken as the only meat'])
def test_chicken_only_meat_keeps_chicken_and_rejects_other_catalog_meat(text):
    rules=interpret(text)
    for name in ['beef','pork','lamb','turkey','salmon','shrimp']:
        assert meal_violations({'name':name,'ingredients':[]},[],rules['excluded'])
    assert not meal_violations({'name':'chicken breast','ingredients':[]},[],rules['excluded'])
    assert not meal_violations({'name':'lentil bowl','ingredients':[]},[],rules['excluded'])


def test_no_red_meat_maps_to_actual_ingredients():
    rules=interpret('No red meat')
    assert meal_violations({'name':'Beef stew','ingredients':[]},[],rules['excluded'])
