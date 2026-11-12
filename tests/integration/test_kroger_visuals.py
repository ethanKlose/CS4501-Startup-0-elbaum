"""Visual data, safe product photos and server-rendered shopping controls."""
import copy

import httpx
import pytest

from app.services import kroger
from app.services.kroger_display import summary,ingredient_icon
from tests.integration.test_kroger import provider,draft,select_first,prefs,review,submit,UPC
from tests.integration.helpers import post

pytestmark=pytest.mark.integration


@pytest.mark.parametrize('url',['http://www.kroger.com/a.jpg','https://kroger.com.evil.test/a.jpg','https://evil.test/a.jpg',
    'javascript:alert(1)','data:image/svg+xml,evil','https://user:pass@www.kroger.com/a.jpg','https://www.kroger.com:8443/a.jpg',
    'https://www.kroger.com/a.jpg\n','https://www.kroger.com:bad/a.jpg'])
def test_untrusted_product_image_urls_are_not_rendered(url):
    assert kroger.product_image([dict(perspective='front',sizes=[dict(size='medium',url=url)])]) is None


def test_front_medium_provider_photo_is_preferred_without_inventing_urls():
    images=[dict(perspective='back',default=True,sizes=[dict(size='medium',url='https://www.kroger.com/back.jpg')]),
        dict(perspective='Front',sizes=[dict(size='thumbnail',url='https://www.kroger.com/thumb.jpg'),
            dict(size='large',url='https://www.kroger.com/large.jpg'),dict(size='medium',url='https://www.kroger.com/medium.jpg')])]
    assert kroger.product_image(images)=='https://www.kroger.com/medium.jpg'
    assert kroger.product_image(None) is None
    assert kroger.product_image([None,dict(sizes='bad'),dict(sizes=[None])]) is None


def test_progress_combines_same_upc_and_does_not_treat_unknown_prices_as_free():
    draft=dict(rows=[dict(selection=dict(upc='a',name='Rice',packages=2,price=3)),
        dict(selection=dict(upc='a',name='Rice',packages=1,price=3)),
        dict(selection=dict(upc='b',name='Bananas',packages=1,price=None)),dict(selection=None)])
    original=copy.deepcopy(draft);result=summary(draft)
    assert result['selected']==3 and result['remaining']==1 and result['total']==4
    assert result['products']==2 and result['packages']==4 and result['known_total']==9 and result['unknown_prices']==1
    assert result['preview'][0]['packages']==3 and result['percent']==75
    assert draft==original
    assert summary(None)['total']==0
    assert ingredient_icon('banana')=='🍌' and ingredient_icon('unknown ingredient')=='🛒'


def test_api_image_becomes_lazy_photo_and_selected_card_and_basket_update(application,web,provider,monkeypatch):
    saved,d=draft(application,web,provider)
    original=provider.handle
    def handler(transport,request):
        response=original(transport,request)
        if request.url.path=='/v1/products':
            body=response.json();body['data'][0]['images']=[dict(perspective='front',sizes=[dict(size='medium',url='https://www.kroger.com/product/images/medium/front/'+UPC)])]
            return httpx.Response(200,json=body)
        return response
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',handler)
    selected=select_first(application,web,d,packages=3)
    page=web.get('/grocery/kroger')
    assert page.status_code==200
    assert 'referrerpolicy="no-referrer"' in page.text and 'loading="lazy"' in page.text
    assert 'https://www.kroger.com/product/images/medium/front/'+UPC in page.text
    assert 'class="kroger-product is-selected' in page.text and 'value="3" required' in page.text
    assert '1 of ' in page.text and '$7.47' in page.text
    assert 'data-testid="kroger-basket-summary"' in page.text
    assert 'data-kroger-filter="remaining"' in page.text and '/static/images/grocery-basket.webp' in page.text
    assert provider.cart_bodies==[]
    # The new display fields must not alter the reviewed cart contract.
    token=review(application,web,selected)
    assert submit(web,selected,token).status_code==303
    assert provider.cart_bodies==[dict(items=[dict(upc=UPC,quantity=3,modality='PICKUP')])]


def test_pre_update_draft_without_photo_metadata_still_renders_and_submits(application,web,provider):
    saved,d=draft(application,web,provider)
    selected=select_first(application,web,d)
    with application.sessions() as db:
        from app.models import User
        from sqlalchemy import select
        from app.services.preferences import get_preferences,save_preferences
        uid=db.scalar(select(User)).id
        data=copy.deepcopy(get_preferences(db,uid))
        for row in data['kroger_draft']['rows']:
            for candidate in row['candidates']:candidate.pop('image_url',None)
            if row['selection']:row['selection'].pop('image_url',None)
        save_preferences(db,uid,data);db.commit()
    page=web.get('/grocery/kroger')
    assert page.status_code==200 and 'Product photo unavailable' in page.text
    assert 'kroger-product is-selected' in page.text
    assert submit(web,selected,review(application,web,selected)).status_code==303


def test_visual_assets_are_served_locally_without_api_requests(application,web,provider):
    saved,d=draft(application,web,provider)
    before=len(provider.calls)
    for path in ['/static/kroger.css','/static/kroger.js','/static/images/grocery-basket.webp']:
        response=web.get(path)
        assert response.status_code==200 and response.content
    assert len(provider.calls)==before
