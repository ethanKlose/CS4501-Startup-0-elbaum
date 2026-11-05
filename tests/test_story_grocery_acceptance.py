"""Stories #22-#26: list normalization, deductions, sections and re-verification."""
from app.services.grocery import build_list,apply_pantry,group_by_section
from app.services.validators import validate_full
from app.services.types import PlanContext,DayCtx
from tests.test_plan import good_plan


def test_mixed_case_and_whitespace_merge_and_partial_pantry_deducts():
    ms=[dict(name='A',ingredients=[dict(name=' RICE ',unit=' CUP ',quantity=2,cost=2,section='pantry')]),
        dict(name='B',ingredients=[dict(name='rice',unit='cup',quantity=3,cost=3,section='produce')])]
    items=build_list(ms)
    assert len(items)==1 and items[0]['unit']=='cup' and items[0]['quantity']==5
    rows=apply_pantry(items,[dict(name='rice',unit='cup',quantity=2)])
    assert rows[0]['quantity']==3 and rows[0]['cost']==3
    grouped=group_by_section(rows)
    assert sum(len(g['entries']) for g in grouped)==len(rows)


def test_duplicate_and_missing_slots_rejected_on_reverification():
    p=good_plan();p['meals'][0]=dict(p['meals'][1])
    _,hard,_=validate_full(p,PlanContext(budget=200,days=[DayCtx(i,45) for i in range(7)]))
    assert any('Missing' in e for e in hard)
    assert any('More than one' in e for e in hard)
