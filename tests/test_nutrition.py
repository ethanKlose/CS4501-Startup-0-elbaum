import copy
import pytest
from app.services.nutrition import INGREDIENTS,calculate,catalog_plan
from tests.test_plan import ctx
from app.services.llm import FakeLLM


def test_usda_snapshot_has_provenance_and_totals_are_recomputed():
    assert INGREDIENTS['banana']['fdc_id']==173944
    cal,pro=calculate([dict(name='banana',unit='each',quantity=1)])
    assert 90<cal<120 and 1<pro<2
    with pytest.raises(ValueError):calculate([dict(name='invented',unit='cup',quantity=1)])


def test_model_cannot_forge_catalog_nutrition_or_instructions():
    context=ctx();good=FakeLLM().generate_plan(context)
    bad=copy.deepcopy(good);bad['meals'][0]['calories']=1;bad['meals'][0]['steps']=['Unsafe made-up instruction']
    hydrated=catalog_plan(bad,context)
    assert hydrated['meals'][0]['calories']==good['meals'][0]['calories']
    assert hydrated['meals'][0]['steps']==good['meals'][0]['steps']
