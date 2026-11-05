import pytest
from app.services.llm import FakeLLM
from app.services.diet import meal_violations
from app.models import Plan
from tests.helpers import signup


@pytest.mark.parametrize('text,terms',[
    ('No peanuts or shellfish',{'peanuts','shellfish'}),
    ('Allergic to peanuts, shellfish',{'peanuts','shellfish'}),
    ('No fish and no dairy',{'fish','dairy'}),
    ('I am vegan',{'vegan'}),
    ("I'm vegetarian",{'vegetarian'}),
])
def test_notes_preserve_all_dietary_constraints(text,terms):
    assert terms<=set(FakeLLM().interpret_preferences(text)['excluded'])


def test_positive_availability_and_numeric_daily_caps():
    llm=FakeLLM()
    assert llm.interpret_preferences('I can cook on Mondays')['day_minutes_cap']=={}
    assert llm.interpret_preferences('I only have 10 minutes to cook each day')['day_minutes_cap']=={str(i):10 for i in range(7)}
    assert llm.interpret_preferences('I am not vegan')['excluded']==[]
    assert llm.interpret_preferences('avoid stone fruit').get('warnings')


@pytest.mark.parametrize('text,diet',[('No peanuts or shellfish',['nut_allergy','shellfish_allergy']),('I am vegan',['vegan'])])
def test_original_note_is_respected_by_saved_plan(client,text,diet):
    signup(client);client.post('/survey',data={'budget':'150','free_text':text})
    client.post('/plan/generate',data={'start_mode':'next_week'})
    with client.app.state.session_factory() as db:
        p=db.query(Plan).first();assert p and len(p.meals)==21
        assert all(not meal_violations(m.as_dict(),diet) for m in p.meals)


def test_live_extraction_cannot_drop_explicit_allergy():
    from tests.test_anthropic_client import client_with
    out=client_with('{"excluded":[],"day_minutes_cap":{}}').interpret_preferences('No peanuts or shellfish')
    assert {'peanuts','shellfish'}<=set(out['excluded'])
