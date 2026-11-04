import copy

import pytest

from app.models import Plan
from app.services.diet import term_hits
from app.services.llm import get_llm
from tests.helpers import signup
from tests.test_plan import Scripted, good_plan


@pytest.mark.parametrize('restriction', ['vegan', 'vegetarian', 'meat'])
def test_chicken_broth_is_never_exempted(restriction):
    assert term_hits('chicken broth', restriction) == ['chicken']


@pytest.mark.parametrize('food', ['almond milk', 'almond butter', 'peanut butter'])
def test_nondairy_substitutes_still_trigger_nut_allergies(food):
    assert term_hits(food, 'nut_allergy')
    assert term_hits(food, 'dairy_free') == []


def test_exception_does_not_hide_another_ingredient():
    assert term_hits('almond milk and dairy milk', 'dairy_free') == ['milk']
    assert term_hits('gluten-free bread', 'gluten_free') == []
    assert term_hits('gluten-free bread and wheat flour', 'gluten_free') == ['flour', 'wheat']
    assert term_hits('nut-free sauce with peanuts', 'nut_allergy') == ['peanuts']
    assert term_hits('eggplant with butternut squash', 'vegan') == []


def test_vegan_broth_response_is_rejected_before_saving(client):
    signup(client)
    client.post('/survey', data={'budget': '200', 'restrictions_present': '1', 'restrictions': 'vegan'})
    bad = copy.deepcopy(good_plan(restrictions=['vegan'], budget=200))
    bad['meals'][0]['ingredients'].append(dict(name='chicken broth', quantity=1, unit='cup', cost=0, section='pantry'))
    llm = Scripted(bad)
    client.app.dependency_overrides[get_llm] = lambda: llm
    client.post('/plan/generate')
    with client.app.state.session_factory() as s:
        assert s.query(Plan).count() == 0
    assert len(llm.calls) == 3
    assert any('vegan' in e for e in llm.calls[1])
