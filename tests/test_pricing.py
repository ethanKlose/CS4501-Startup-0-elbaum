from app.services.pricing import checkout


def test_whole_packages_round_up_and_preserve_price_source():
    items=[dict(key='rice|cup',name='rice',unit='cup',quantity=4.1,cost=1)]
    offer={'rice|cup':dict(package_quantity=4,package_price=3,source='Receipt',observed_on='2026-11-01')}
    result=checkout(items,offer)[0]
    assert result['packages']==2 and result['checkout_cost']==6
    assert result['extra_quantity']==3.9 and result['price_source']=='Receipt'


def test_demo_planner_optimizes_checkout_budget_across_seeds():
    from app.services.llm import FakeLLM
    from app.services.types import PlanContext,DayCtx
    from app.services.validators import check_checkout_budget
    for seed in [1,23,147,7919,39241,526417]:
        ctx=PlanContext(budget=100,days=[DayCtx(i,45) for i in range(7)],checkout_budget=True,seed=seed)
        assert check_checkout_budget(FakeLLM().generate_plan(ctx),ctx)==[]


def test_legacy_unknown_prices_are_visible_but_not_accepted_as_verified_packages():
    import pytest
    item=dict(key='legacy powder|scoop',name='legacy powder',unit='scoop',quantity=1,cost=2)
    with pytest.raises(ValueError):checkout([item])
    row=checkout([item],allow_unknown=True)[0]
    assert row['unknown_package'] and row['checkout_cost']==2
