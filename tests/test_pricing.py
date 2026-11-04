from app.services.pricing import checkout


def test_whole_packages_round_up_and_preserve_price_source():
    items=[dict(key='rice|cup',name='rice',unit='cup',quantity=4.1,cost=1)]
    offer={'rice|cup':dict(package_quantity=4,package_price=3,source='Receipt',observed_on='2026-11-01')}
    result=checkout(items,offer)[0]
    assert result['packages']==2 and result['checkout_cost']==6
    assert result['extra_quantity']==3.9 and result['price_source']=='Receipt'
